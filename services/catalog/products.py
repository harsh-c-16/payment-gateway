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
    p.material, p.seller_id, p.price_minor, p.retail_price_minor, p.rating, p.inactive_reason"""


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
