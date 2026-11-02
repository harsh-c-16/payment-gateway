"""Hard filters and ranking for /v1/search. Filters always run before any ranking."""

from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from pipelines.catalog.normalize import clean_text, load_dictionary
from services.catalog.errors import ServiceError
from services.catalog.products import dataset_revision
from shared.contracts.catalog import ProductHit, SearchResponse
from shared.contracts.common import ErrorCode

DICTIONARY = load_dictionary()
ROOTS = set(DICTIONARY["root_ids"].values())
SIZES = set(DICTIONARY["allowed_apparel_sizes"])
CANDIDATE_LIMIT = 100
# Any matching term counts; ts_rank then rewards documents matching more terms and the title.
TSQUERY = "replace(plainto_tsquery('english', %(text)s)::text, ' & ', ' | ')::tsquery"
HIT_COLUMNS = """p.sku, p.product_id, p.title, p.category, p.brand, p.size, p.colour, p.material,
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


def filter_catalog(tx, intent, namespace):
    """Eligible count under every hard constraint. Returns (where, parameters, count)."""
    where, parameters = hard_filters(intent, namespace)
    count = tx.execute(
        f"SELECT count(*) AS n FROM {FROM_ELIGIBLE} WHERE {where}", parameters
    ).fetchone()["n"]
    return where, parameters, count


def rank_filter_only(tx, where, parameters, limit, _text):
    rows = tx.execute(
        f"""SELECT {HIT_COLUMNS}, 0.0::float8 AS score, count(*) OVER () AS candidates
        FROM {FROM_ELIGIBLE} WHERE {where} ORDER BY p.price_minor, p.sku LIMIT %(limit)s""",
        {**parameters, "limit": limit},
    ).fetchall()
    return rows


def rank_lexical(tx, where, parameters, limit, text):
    has_terms = tx.execute(f"SELECT numnode({TSQUERY}) > 0 AS terms", {"text": text}).fetchone()[
        "terms"
    ]
    if not has_terms:
        # Structured search without text: every eligible listing is an equal candidate.
        return tx.execute(
            f"""SELECT {HIT_COLUMNS}, 0.0::float8 AS score, count(*) OVER () AS candidates
            FROM {FROM_ELIGIBLE} WHERE {where} ORDER BY p.sku LIMIT %(limit)s""",
            {**parameters, "limit": limit},
        ).fetchall()
    return tx.execute(
        f"""WITH ranked AS (
                SELECT {HIT_COLUMNS}, ts_rank(p.search_vector, {TSQUERY})::float8 AS score,
                       count(*) OVER () AS candidates
                FROM {FROM_ELIGIBLE} WHERE {where} AND p.search_vector @@ {TSQUERY}
            )
            SELECT * FROM ranked ORDER BY score DESC, sku LIMIT %(limit)s""",
        {**parameters, "limit": limit, "text": text},
    ).fetchall()


RANKERS = {"filter_only": rank_filter_only, "lexical": rank_lexical}


def fuse_rrf(lexical_ranked, vector_ranked, k=60, top_k=5):
    """Reciprocal rank fusion over already-eligible SKUs; ties break on SKU."""
    scores = {}
    for ranked in (lexical_ranked, vector_ranked):
        for rank, sku in enumerate(ranked, 1):
            scores[sku] = scores.get(sku, 0.0) + 1 / (k + rank)
    ordered = sorted(scores, key=lambda sku: (-scores[sku], sku))
    return [(sku, scores[sku]) for sku in ordered[:top_k]]


def search_catalog(db, events, request, context):
    """Search plus SEARCH_REQUESTED/PRODUCT_RETRIEVED in one local transaction."""
    ranker = RANKERS.get(request.mode)
    if ranker is None:
        raise ServiceError(
            503,
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            "Vector retrieval modes are not provisioned in this deployment.",
            details={"mode": request.mode},
        )
    total_start = perf_counter()
    search_id = str(uuid4())
    namespace = context.namespace
    with db.transaction() as tx:
        started = perf_counter()
        where, parameters, eligible = filter_catalog(tx, request.intent, namespace)
        filter_ms = (perf_counter() - started) * 1000
        started = perf_counter()
        rows = ranker(tx, where, parameters, request.top_k, request.intent.query_text)
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
            candidate_count=candidates,
            eligible_count=eligible,
            returned_count=len(hits),
            exhausted=len(hits) == candidates,
            embedding_revision=None,
            timings_ms={
                "embedding": 0,
                "filter": filter_ms,
                "rank": rank_ms,
                "total": (perf_counter() - total_start) * 1000,
            },
            embedding_calls=0,
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
