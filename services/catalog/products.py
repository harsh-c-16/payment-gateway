"""Product lookup, facets, quotes and authoritative price changes."""

from services.catalog.errors import not_found
from shared.contracts.catalog import Product, StockSnapshot

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
