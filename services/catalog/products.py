"""Product lookup, facets, quotes and authoritative price changes."""

import hashlib
from datetime import timedelta
from uuid import uuid4

from psycopg.types.json import Jsonb

from services.catalog.errors import ServiceError, not_found
from shared.contracts.catalog import Product, Quote, QuoteLine, StockSnapshot
from shared.contracts.common import ErrorCode
from shared.event_transport.schemas import canonical_json

PRODUCT_COLUMNS = """p.product_id, p.sku, p.title, p.category_path AS category_path_normalized,
    p.attributes, p.quality_flags, p.dataset_revision, p.source_pid, p.source_observation_id,
    p.source_crawled_at, p.currency, p.currency_source, p.catalog_version, p.active,
    p.description, p.category, p.brand, p.brand_normalized, p.size, p.size_kind, p.colour,
    p.material, p.seller_id, p.price_minor, p.retail_price_minor, p.rating, p.inactive_reason,
    p.image_urls"""


def dataset_revision(tx, namespace):
    row = tx.execute(
        "SELECT dataset_revision FROM catalog_imports WHERE namespace=%s AND status='complete' "
        "ORDER BY completed_at DESC LIMIT 1",
        (namespace,),
    ).fetchone()
    if row is None:
        raise not_found("Catalogue for this namespace")
    return row["dataset_revision"]


def get_product(db, namespace, sku):
    with db.transaction() as tx:
        row = tx.execute(
            f"SELECT {PRODUCT_COLUMNS} FROM products p WHERE p.namespace=%s AND p.sku=%s",
            (namespace, sku),
        ).fetchone()
        if row is None:
            raise not_found("Product")
        stock = tx.execute(
            "SELECT sku,on_hand,reserved,available,stock_version,changed_at "
            "FROM stock_projection WHERE namespace=%s AND sku=%s",
            (namespace, sku),
        ).fetchone()
    return {"product": Product(**row), "stock": StockSnapshot(**stock) if stock else None}


def get_facets(db, namespace, revision=None):
    with db.transaction() as tx:
        revision = revision or dataset_revision(tx, namespace)
        row = tx.execute(
            "SELECT document FROM facet_dictionaries WHERE namespace=%s AND dataset_revision=%s",
            (namespace, revision),
        ).fetchone()
    if row is None:
        raise not_found("Facet dictionary")
    return row["document"]


def browse(db, namespace, *, query, category, max_price_minor, sort, offset, limit):
    """Read-only storefront listing over the same sellable set and hard filters."""
    from services.catalog.search import (
        FROM_ELIGIBLE,
        HIT_COLUMNS,
        TSQUERY,
        hard_filters,
        lexical_eligibility,
    )
    from shared.contracts.catalog import ProductHit, ProductPage, ShoppingIntent

    intent = ShoppingIntent(
        query_text=query,
        category=category,
        size=None,
        colour=None,
        material=None,
        max_price_minor=max_price_minor,
        occasion=None,
    )
    where, parameters = hard_filters(intent, namespace)
    from services.catalog.product_types import restrict_product_type

    where, parameters = restrict_product_type(where, parameters, query)
    score = f"ts_rank(p.search_vector, {TSQUERY})::float8" if query.strip() else "0.0::float8"
    order = {
        "relevance": "score DESC, p.sku",
        "price_asc": "p.price_minor, p.sku",
        "price_desc": "p.price_minor DESC, p.sku",
    }[sort]
    parameters.update(text=query, limit=limit, offset=offset)
    with db.transaction() as tx:
        if query.strip():
            # This bounded UI query materializes about 10 MiB on the retained catalogue.
            # Avoid spilling that eligible set to disk at the default 4 MiB. Ranking,
            # filters, deadlines and the evaluated /v1/search path remain unchanged.
            tx.execute("SET LOCAL work_mem = '16MB'")
            eligible = lexical_eligibility(where)
            matches = f"FROM eligible p WHERE p.search_vector @@ {TSQUERY}"
            found = tx.execute(
                f"""{eligible}, page AS MATERIALIZED (
                    SELECT p.namespace, p.sku, {score} AS score,
                           count(*) OVER () AS total {matches}
                    ORDER BY {order} LIMIT %(limit)s OFFSET %(offset)s
                )
                SELECT {HIT_COLUMNS}, page.score, page.total FROM page
                JOIN products p ON p.namespace=page.namespace AND p.sku=page.sku
                JOIN stock_projection s ON s.namespace=p.namespace AND s.sku=p.sku
                ORDER BY {order}""",
                parameters,
            ).fetchall()
            total = found[0]["total"] if found else 0
            for row in found:
                del row["total"]
            # An empty page past the end still reports the real matching count.
            if not found and offset:
                total = tx.execute(
                    f"{eligible} SELECT count(*) AS n {matches}", parameters
                ).fetchone()["n"]
        else:
            total = tx.execute(
                f"SELECT count(*) AS n FROM {FROM_ELIGIBLE} WHERE {where}", parameters
            ).fetchone()["n"]
            found = tx.execute(
                f"SELECT {HIT_COLUMNS}, {score} AS score FROM {FROM_ELIGIBLE} WHERE {where} "
                f"ORDER BY {order} LIMIT %(limit)s OFFSET %(offset)s",
                parameters,
            ).fetchall()
    return ProductPage(
        items=[
            ProductHit(**row, retrieval_mode="lexical", rank=offset + i)
            for i, row in enumerate(found, 1)
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


def _claim(tx, namespace, scope, operation, key, request):
    """Returns the stored response for a replay, None for a first execution.

    The insert waits on a concurrent holder of the same key, so at most one transaction runs
    the effect. Its placeholder response is replaced by _complete in the same transaction.
    """
    digest = hashlib.sha256(canonical_json(request)).hexdigest()
    claimed = tx.execute(
        "INSERT INTO operation_keys (namespace,scope,operation,key,request_hash,response) "
        "VALUES (%s,%s,%s,%s,%s,'{}') ON CONFLICT DO NOTHING RETURNING 1 AS claimed",
        (namespace, scope, operation, key, digest),
    ).fetchone()
    if claimed:
        return None
    previous = tx.execute(
        "SELECT request_hash,response FROM operation_keys "
        "WHERE namespace=%s AND scope=%s AND operation=%s AND key=%s",
        (namespace, scope, operation, key),
    ).fetchone()
    if previous["request_hash"] != digest:
        raise ServiceError(
            409,
            ErrorCode.IDEMPOTENCY_CONFLICT,
            "Idempotency-Key was already used with a different request.",
        )
    return previous["response"]


def _complete(tx, namespace, scope, operation, key, response):
    tx.execute(
        "UPDATE operation_keys SET response=%s "
        "WHERE namespace=%s AND scope=%s AND operation=%s AND key=%s",
        (Jsonb(response), namespace, scope, operation, key),
    )


def create_quote(db, request, context, key, *, ttl_seconds=60):
    """Prices from one statement snapshot; client display prices are never read."""
    namespace = context.namespace
    with db.transaction() as tx:
        replay = _claim(
            tx, namespace, context.user_id, "quote", key, request.model_dump(mode="json")
        )
        if replay is not None:
            return Quote(**replay)
        rows = tx.execute(
            "SELECT sku,price_minor,catalog_version,active,inactive_reason FROM products "
            "WHERE namespace=%s AND sku = ANY(%s)",
            (namespace, [line.sku for line in request.lines]),
        ).fetchall()
        priced = {row["sku"]: row for row in rows}
        lines = []
        for line in request.lines:
            row = priced.get(line.sku)
            if row is None:
                raise not_found("Product")
            if not row["active"] or row["price_minor"] is None:
                raise ServiceError(
                    409,
                    ErrorCode.PRODUCT_NOT_SELLABLE,
                    "Listing cannot be quoted.",
                    details={"sku": line.sku, "reason": row["inactive_reason"]},
                )
            lines.append(
                QuoteLine(
                    sku=line.sku,
                    quantity=line.quantity,
                    unit_price_minor=row["price_minor"],
                    line_total_minor=row["price_minor"] * line.quantity,
                    catalog_version=row["catalog_version"],
                )
            )
        created_at = tx.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
        quote = Quote(
            quote_id=str(uuid4()),
            user_id=context.user_id,
            cart_id=request.cart_id,
            cart_version=request.cart_version,
            lines=lines,
            total_amount_minor=sum(line.line_total_minor for line in lines),
            currency="INR",
            created_at=created_at,
            expires_at=created_at + timedelta(seconds=ttl_seconds),
        )
        tx.execute(
            "INSERT INTO quotes (namespace,quote_id,user_id,cart_id,cart_version,"
            "total_amount_minor,currency,created_at,expires_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                namespace,
                quote.quote_id,
                quote.user_id,
                quote.cart_id,
                quote.cart_version,
                quote.total_amount_minor,
                quote.currency,
                quote.created_at,
                quote.expires_at,
            ),
        )
        with tx.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO quote_lines (namespace,quote_id,sku,quantity,unit_price_minor,"
                "line_total_minor,catalog_version) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                [
                    (
                        namespace,
                        quote.quote_id,
                        line.sku,
                        line.quantity,
                        line.unit_price_minor,
                        line.line_total_minor,
                        line.catalog_version,
                    )
                    for line in quote.lines
                ],
            )
        _complete(tx, namespace, context.user_id, "quote", key, quote.model_dump(mode="json"))
    return quote


def get_quote(db, namespace, quote_id, user_id):
    """An expired quote is returned with its past expires_at; Orders enforces validity."""
    with db.transaction() as tx:
        row = tx.execute(
            "SELECT quote_id,user_id,cart_id,cart_version,total_amount_minor,currency,"
            "created_at,expires_at FROM quotes WHERE namespace=%s AND quote_id=%s",
            (namespace, quote_id),
        ).fetchone()
        if row is None:
            raise not_found("Quote")
        if row["user_id"] != user_id:
            raise ServiceError(403, ErrorCode.FORBIDDEN, "Quote belongs to another user.")
        lines = tx.execute(
            "SELECT sku,quantity,unit_price_minor,line_total_minor,catalog_version "
            "FROM quote_lines WHERE namespace=%s AND quote_id=%s ORDER BY sku",
            (namespace, quote_id),
        ).fetchall()
    return Quote(
        **{**row, "quote_id": str(row["quote_id"]), "cart_id": str(row["cart_id"])}, lines=lines
    )


def update_price(db, events, sku, request, context, key):
    """Price, catalog_version and PRICE_UPDATED commit together; stock is untouched."""
    namespace = context.namespace
    with db.transaction() as tx:
        scope = "internal:" + sku
        replay = _claim(tx, namespace, scope, "price", key, request.model_dump(mode="json"))
        if replay is not None:
            return Product(**replay)
        current = tx.execute(
            "SELECT active,catalog_version FROM products WHERE namespace=%s AND sku=%s FOR UPDATE",
            (namespace, sku),
        ).fetchone()
        if current is None:
            raise not_found("Product")
        if not current["active"]:
            raise ServiceError(
                409, ErrorCode.PRODUCT_NOT_SELLABLE, "Inactive listing has no live price."
            )
        if current["catalog_version"] != request.expected_catalog_version:
            raise ServiceError(
                409,
                ErrorCode.ILLEGAL_STATE,
                "Catalogue version changed.",
                details={"catalog_version": str(current["catalog_version"])},
            )
        # The source-derived hash must also change: a later re-import then sees a real difference.
        row = tx.execute(
            f"""UPDATE products p SET price_minor=%(price)s, catalog_version=catalog_version+1,
                normalized_business_hash=encode(sha256(convert_to(
                    normalized_business_hash || ':price:' || %(price)s::text, 'UTF8')), 'hex')
            WHERE namespace=%(namespace)s AND sku=%(sku)s RETURNING {PRODUCT_COLUMNS}""",
            {"price": request.price_minor, "namespace": namespace, "sku": sku},
        ).fetchone()
        product = Product(**row)
        occurred_at = tx.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
        events.append(
            tx,
            event_type="PRICE_UPDATED",
            payload={
                "sku": sku,
                "price_minor": product.price_minor,
                "currency": product.currency,
                "catalog_version": product.catalog_version,
            },
            context=context,
            aggregate_type="sku",
            aggregate_id=sku,
            aggregate_version=product.catalog_version,
            event_time=occurred_at,
            metadata={
                "dataset_revision": product.dataset_revision,
                "synthetic": True,
                "scenario_source": "simulation",
            },
        )
        _complete(tx, namespace, scope, "price", key, product.model_dump(mode="json"))
    return product
