"""Hard filters and ranking for /v1/search. Filters always run before any ranking."""

from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from pipelines.catalog.normalize import clean_text, load_dictionary
from services.catalog.embedding import load_lock, vector_text
from services.catalog.errors import ServiceError
from services.catalog.product_types import restrict_product_type
from services.catalog.products import dataset_revision
from shared.contracts.catalog import ProductHit, SearchResponse
from shared.contracts.common import ErrorCode

DICTIONARY = load_dictionary()
ROOTS = set(DICTIONARY["root_ids"].values())
SIZES = set(DICTIONARY["allowed_apparel_sizes"])
CANDIDATE_LIMIT = 100
ANN_DEFAULTS = {"ef_search": 100, "iterative_scan": "strict_order"}
# Any matching term counts; ts_rank then rewards documents matching more terms and the title.
TSQUERY = "replace(plainto_tsquery('english', %(text)s)::text, ' & ', ' | ')::tsquery"
HIT_COLUMNS = """p.sku, p.product_id, p.title, p.category, p.brand, p.size, p.colour, p.material,
    p.image_urls,
    p.price_minor, p.currency, p.catalog_version, p.dataset_revision, p.quality_flags,
    s.available AS stock_available, s.stock_version, s.changed_at AS stock_updated_at,
    s.applied_at AS stock_applied_at"""
FROM_ELIGIBLE = """products p
    JOIN stock_projection s ON s.namespace = p.namespace AND s.sku = p.sku"""


def facet_value(value):
    return clean_text(value).casefold()


def hard_filters(intent, namespace):
    """Returns (WHERE text, parameters). Unknown projection is unavailable: inner join above."""
    clauses = ["p.namespace = %(namespace)s", "p.active", "s.available > 0"]
    parameters = {"namespace": namespace}
    if intent.category is not None:
        if intent.category not in ROOTS:
            raise ServiceError(
                422,
                ErrorCode.UNSUPPORTED_FILTER,
                "Unsupported category.",
                details={"field": "category"},
            )
        clauses.append("p.category = %(category)s")
        parameters["category"] = intent.category
    if intent.size is not None:
        if intent.size not in SIZES:
            raise ServiceError(
                422, ErrorCode.UNSUPPORTED_FILTER, "Unsupported size.", details={"field": "size"}
            )
        clauses.append("p.size = %(size)s")
        parameters["size"] = intent.size
    if intent.colour is not None:
        colour = facet_value(intent.colour)
        clauses.append("p.colour = %(colour)s")
        parameters["colour"] = "grey" if colour == "gray" else colour
    if intent.material is not None:
        clauses.append("p.material = %(material)s")
        parameters["material"] = facet_value(intent.material)
    if intent.brand is not None:
        clauses.append("p.brand_normalized = %(brand)s")
        parameters["brand"] = facet_value(intent.brand)
    if intent.max_price_minor is not None:
        clauses.append("p.price_minor <= %(max_price)s")
        parameters["max_price"] = intent.max_price_minor
    if intent.category_path_prefix is not None:
        prefix = [clean_text(segment) for segment in intent.category_path_prefix]
        if not prefix or not all(prefix):
            raise ServiceError(
                422,
                ErrorCode.UNSUPPORTED_FILTER,
                "Unsupported category path prefix.",
                details={"field": "category_path_prefix"},
            )
        # Whole segments, case-folded by the same function that built category_path_folded.
        clauses.append(
            "p.category_path_folded[1:%(depth)s] = "
            "ARRAY(SELECT lower(segment) FROM unnest(%(prefix)s::text[]) AS segment)"
        )
        parameters.update(depth=len(prefix), prefix=prefix)
    return " AND ".join(clauses), parameters


def filter_catalog(tx, intent, namespace, exclude_skus=()):
    """Eligible count under every hard constraint. Returns (where, parameters, count)."""
    where, parameters = hard_filters(intent, namespace)
    if exclude_skus:
        where += " AND NOT (p.sku = ANY(%(exclude_skus)s))"
        parameters["exclude_skus"] = list(exclude_skus)
    count = tx.execute(
        f"SELECT count(*) AS n FROM {FROM_ELIGIBLE} WHERE {where}", parameters
    ).fetchone()["n"]
    return where, parameters, count


def rank_filter_only(tx, where, parameters, limit, _text, _vector):
    rows = tx.execute(
        f"""SELECT {HIT_COLUMNS}, 0.0::float8 AS score, count(*) OVER () AS candidates
        FROM {FROM_ELIGIBLE} WHERE {where} ORDER BY p.price_minor, p.sku LIMIT %(limit)s""",
        {**parameters, "limit": limit},
    ).fetchall()
    return rows


def has_terms(tx, text):
    return tx.execute(f"SELECT numnode({TSQUERY}) > 0 AS terms", {"text": text}).fetchone()["terms"]


def lexical_eligibility(where):
    # Prevent PostgreSQL from reading toasted text for other namespaces/ineligible products.
    return f"""WITH eligible AS MATERIALIZED (
        SELECT p.namespace, p.sku, p.price_minor, p.search_vector
        FROM {FROM_ELIGIBLE} WHERE {where}
    )"""


def rank_lexical(tx, where, parameters, limit, text, _vector):
    if not has_terms(tx, text):
        # Structured search without text: every eligible listing is an equal candidate.
        return tx.execute(
            f"""SELECT {HIT_COLUMNS}, 0.0::float8 AS score, count(*) OVER () AS candidates
            FROM {FROM_ELIGIBLE} WHERE {where} ORDER BY p.sku LIMIT %(limit)s""",
            {**parameters, "limit": limit},
        ).fetchall()
    rows = tx.execute(
        f"""{lexical_eligibility(where)}
            SELECT sku, ts_rank(search_vector, {TSQUERY})::float8 AS score,
                   count(*) OVER () AS candidates
            FROM eligible WHERE search_vector @@ {TSQUERY}
            ORDER BY score DESC, sku LIMIT %(limit)s""",
        {**parameters, "limit": limit, "text": text},
    ).fetchall()
    return hydrate(
        tx,
        where,
        parameters,
        [(row["sku"], row["score"]) for row in rows],
        rows[0]["candidates"] if rows else 0,
    )


def fuse_rrf(lexical_ranked, vector_ranked, k=60, top_k=5):
    """Reciprocal rank fusion over already-eligible SKUs; ties break on SKU."""
    scores = {}
    for ranked in (lexical_ranked, vector_ranked):
        for rank, sku in enumerate(ranked, 1):
            scores[sku] = scores.get(sku, 0.0) + 1 / (k + rank)
    ordered = sorted(scores, key=lambda sku: (-scores[sku], sku))
    return [(sku, scores[sku]) for sku in ordered[:top_k]]


def exact_search(tx, where, parameters, vector, limit):
    """Exact cosine ranking over eligible rows. The materialized CTE cannot use an ANN index."""
    return tx.execute(
        f"""WITH eligible AS MATERIALIZED (
                SELECT p.sku, p.embedding FROM {FROM_ELIGIBLE}
                WHERE {where} AND p.embedding IS NOT NULL
            )
            SELECT sku, embedding <=> %(vector)s::vector AS distance
            FROM eligible ORDER BY distance, sku LIMIT %(limit)s""",
        {**parameters, "vector": vector, "limit": limit},
    ).fetchall()


def ann_search(tx, where, parameters, vector, limit, ann_config=ANN_DEFAULTS):
    """HNSW branch with no exact fallback, so a filtered shortage stays visible to the caller.

    The planner settings hold only for this transaction: they stop it answering a raw ANN trial
    with an exact plan, which would hide the recall this variant exists to measure.
    """
    for name, value in (
        ("hnsw.ef_search", str(ann_config["ef_search"])),
        ("hnsw.iterative_scan", ann_config["iterative_scan"]),
        ("enable_seqscan", "off"),
        ("enable_bitmapscan", "off"),
        ("enable_sort", "off"),
    ):
        tx.execute("SELECT set_config(%s, %s, true)", (name, value))
    return tx.execute(
        f"""SELECT p.sku, p.embedding <=> %(vector)s::vector AS distance
            FROM {FROM_ELIGIBLE} WHERE {where} AND p.embedding IS NOT NULL
            ORDER BY p.embedding <=> %(vector)s::vector LIMIT %(limit)s""",
        {**parameters, "vector": vector, "limit": limit},
    ).fetchall()


def hydrate(tx, where, parameters, ranked, candidates):
    """Full hit rows for SKUs ranked elsewhere, re-checked against the same hard filters."""
    if not ranked:
        return []
    rows = tx.execute(
        f"SELECT {HIT_COLUMNS} FROM {FROM_ELIGIBLE} WHERE {where} AND p.sku = ANY(%(ranked_skus)s)",
        {**parameters, "ranked_skus": [sku for sku, _ in ranked]},
    ).fetchall()
    by_sku = {row["sku"]: row for row in rows}
    return [
        {**by_sku[sku], "score": score, "candidates": candidates}
        for sku, score in ranked
        if sku in by_sku
    ]


def rank_vector_exact(tx, where, parameters, limit, _text, vector):
    rows = exact_search(tx, where, parameters, vector, limit)
    return hydrate(tx, where, parameters, [(r["sku"], 1 - r["distance"]) for r in rows], len(rows))


def _rank_hybrid(tx, where, parameters, limit, text, vector, branch):
    # Stopwords alone give no lexical ranking; SKU order must not pose as one in the fusion.
    lexical = (
        [row["sku"] for row in rank_lexical(tx, where, parameters, CANDIDATE_LIMIT, text, None)]
        if has_terms(tx, text)
        else []
    )
    semantic = [row["sku"] for row in branch(tx, where, parameters, vector, CANDIDATE_LIMIT)]
    fused = fuse_rrf(lexical, semantic, k=60, top_k=limit)
    return hydrate(tx, where, parameters, fused, len(set(lexical) | set(semantic)))


def rank_hybrid_exact(tx, where, parameters, limit, text, vector):
    return _rank_hybrid(tx, where, parameters, limit, text, vector, exact_search)


def rank_hybrid_ann(tx, where, parameters, limit, text, vector):
    return _rank_hybrid(tx, where, parameters, limit, text, vector, ann_search)


RANKERS = {
    "filter_only": rank_filter_only,
    "lexical": rank_lexical,
    "vector_exact": rank_vector_exact,
    "hybrid_exact": rank_hybrid_exact,
    "hybrid_ann": rank_hybrid_ann,
}
VECTOR_MODES = {"vector_exact", "hybrid_exact", "hybrid_ann"}


def query_embedding(request, encoder):
    """Encoded before any database work, so no connection is held during inference.

    Returns (vector text or None, elapsed ms, calls). Occasion guides semantic ranking only.
    """
    intent = request.intent
    text = " ".join(part for part in (intent.query_text, intent.occasion) if part).strip()
    if request.mode not in VECTOR_MODES or not text:
        return None, 0.0, 0
    if encoder is None:
        raise ServiceError(
            503,
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            "Vector retrieval modes are not provisioned in this deployment.",
            details={"mode": request.mode},
        )
    started = perf_counter()
    vectors, _ = encoder.encode([text])
    return vector_text(vectors[0]), (perf_counter() - started) * 1000, 1


def search_catalog(db, events, request, context, *, encoder=None, frozen_vector=None):
    """Search plus SEARCH_REQUESTED/PRODUCT_RETRIEVED in one local transaction.

    frozen_vector lets exact-versus-ANN trials reuse one saved query embedding.
    """
    total_start = perf_counter()
    if frozen_vector is not None:
        vector, embedding_ms, embedding_calls = frozen_vector, 0.0, 0
    else:
        vector, embedding_ms, embedding_calls = query_embedding(request, encoder)
    # No text means nothing to embed: every eligible listing is an equal lexical candidate.
    ranker = (
        RANKERS[request.mode]
        if vector is not None or request.mode not in VECTOR_MODES
        else (rank_lexical)
    )
    search_id = str(uuid4())
    namespace = context.namespace
    with db.transaction() as tx:
        started = perf_counter()
        where, parameters, eligible = filter_catalog(
            tx, request.intent, namespace, request.exclude_skus
        )
        if vector is not None:
            # Do not fuse vectors from another model, or silently omit unembedded products.
            revision = encoder.revision if encoder is not None else load_lock()["revision"]
            incomplete = tx.execute(
                f"SELECT count(*) AS n FROM {FROM_ELIGIBLE} WHERE {where} "
                "AND (p.embedding IS NULL OR p.embedding_revision IS DISTINCT FROM %(revision)s)",
                {**parameters, "revision": revision},
            ).fetchone()["n"]
            if incomplete:
                raise ServiceError(
                    503,
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "Vector retrieval needs current embeddings for every eligible product.",
                    details={"mode": request.mode},
                )
        filter_ms = (perf_counter() - started) * 1000
        started = perf_counter()
        rank_where, rank_parameters = restrict_product_type(
            where, parameters, request.intent.query_text
        )
        rows = ranker(
            tx, rank_where, rank_parameters, request.top_k, request.intent.query_text, vector
        )
        rank_ms = (perf_counter() - started) * 1000
        candidates = rows[0]["candidates"] if rows else 0
        hits = [
            ProductHit(
                **{key: value for key, value in row.items() if key != "candidates"},
                retrieval_mode=request.mode,
                rank=rank,
            )
            for rank, row in enumerate(rows, 1)
        ]
        served_at = datetime.now(UTC)
        response = SearchResponse(
            search_id=search_id,
            hits=hits,
            mode=request.mode,
            # The pool a ranker may consider is the eligible set, so consumers can rely on
            # candidate >= eligible >= returned. Text matches only decide `exhausted`.
            candidate_count=eligible,
            eligible_count=eligible,
            returned_count=len(hits),
            exhausted=len(hits) == candidates,
            embedding_revision=encoder.revision if embedding_calls else None,
            timings_ms={
                "embedding": embedding_ms,
                "filter": filter_ms,
                "rank": rank_ms,
                "total": (perf_counter() - total_start) * 1000,
            },
            embedding_calls=embedding_calls,
            served_at=served_at,
        )
        revision = dataset_revision(tx, namespace)
        scoped = context.model_copy(update={"session_id": request.session_id})
        metadata = {
            "dataset_revision": revision,
            "synthetic": True,
            "scenario_source": "simulation",
        }
        for version, (event_type, payload) in enumerate(
            (
                (
                    "SEARCH_REQUESTED",
                    {
                        "search_id": search_id,
                        "intent": request.intent.model_dump(mode="json"),
                        "mode": request.mode,
                    },
                ),
                (
                    "PRODUCT_RETRIEVED",
                    {
                        "search_id": search_id,
                        "skus": [hit.sku for hit in hits],
                        "returned_count": len(hits),
                        "mode": request.mode,
                        "duration_ms": response.timings_ms.total,
                    },
                ),
            ),
            1,
        ):
            events.append(
                tx,
                event_type=event_type,
                payload=payload,
                context=scoped,
                aggregate_type="search",
                aggregate_id=search_id,
                aggregate_version=version,
                event_time=served_at,
                metadata=metadata,
            )
    return response
