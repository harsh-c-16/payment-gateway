"""M2 wire DTOs (common §4 and Appendix A): catalogue, search, quotes and data manifests."""

from typing import Annotated, Literal

from pydantic import Field, StringConstraints, model_validator

from shared.contracts.analytics import FileDescriptor
from shared.contracts.common import Identifier, Money, Sku, UTCTime, UUIDText, WireModel

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
UnitPrice = Annotated[int, Field(strict=True, ge=1, le=1_000_000_000)]
Quantity = Annotated[int, Field(strict=True, ge=1, le=10)]
CatalogVersion = Annotated[int, Field(strict=True, ge=1)]
Count = Annotated[int, Field(strict=True, ge=0)]
Currency = Literal["INR"]
# Same bounds as the retrieval event schema, so a request it would refuse fails as a 422 here.
Facet = Annotated[str, Field(min_length=1, max_length=256)]
SearchMode = Literal["filter_only", "lexical", "vector_exact", "hybrid_exact", "hybrid_ann"]


class ShoppingIntent(WireModel):
    query_text: Annotated[str, Field(max_length=2000)]
    category: Facet | None
    size: Facet | None
    colour: Facet | None
    material: Facet | None
    max_price_minor: Money | None
    occasion: Facet | None
    currency: Currency = "INR"
    brand: Facet | None = None
    category_path_prefix: list[Facet] | None = None


class SearchRequest(WireModel):
    request_id: UUIDText
    session_id: UUIDText
    intent: ShoppingIntent
    top_k: Annotated[int, Field(strict=True, ge=1, le=20)] = 5
    mode: SearchMode = "lexical"


class ProductHit(WireModel):
    sku: Sku
    product_id: Sku
    title: str
    category: str | None
    brand: str | None
    size: str | None
    colour: str | None
    material: str | None
    price_minor: UnitPrice
    currency: Currency
    catalog_version: CatalogVersion
    dataset_revision: str
    quality_flags: list[str]
    score: float
    stock_available: Count
    stock_version: CatalogVersion
    stock_updated_at: UTCTime
    stock_applied_at: UTCTime
    retrieval_mode: SearchMode
    rank: CatalogVersion


class SearchTimings(WireModel):
    embedding: Annotated[float, Field(ge=0)]
    filter: Annotated[float, Field(ge=0)]
    rank: Annotated[float, Field(ge=0)]
    total: Annotated[float, Field(ge=0)]


class SearchResponse(WireModel):
    search_id: UUIDText
    hits: Annotated[list[ProductHit], Field(max_length=20)]
    mode: SearchMode
    candidate_count: Count
    eligible_count: Count
    returned_count: Count
    exhausted: bool
    embedding_revision: str | None
    timings_ms: SearchTimings
    embedding_calls: Count
    served_at: UTCTime


class Product(WireModel):
    product_id: Sku
    sku: Sku
    title: str
    category_path_normalized: list[str]
    attributes: dict[str, list[str]]
    quality_flags: list[str]
    dataset_revision: str
    source_pid: str
    source_observation_id: str
    source_crawled_at: UTCTime
    currency: Currency
    currency_source: Literal["project_assumption"]
    catalog_version: CatalogVersion
    active: bool
    description: str | None
    category: str | None
    brand: str | None
    brand_normalized: str | None
    size: str | None
    size_kind: str | None
    colour: str | None
    material: str | None
    seller_id: str | None
    price_minor: UnitPrice | None
    retail_price_minor: UnitPrice | None
    rating: str | None
    inactive_reason: str | None


class StockSnapshot(WireModel):
    sku: Sku
    on_hand: Count
    reserved: Count
    available: Count
    stock_version: CatalogVersion
    changed_at: UTCTime


class ProductResponse(WireModel):
    product: Product
    stock: StockSnapshot | None


class QuoteRequestLine(WireModel):
    sku: Sku
    quantity: Quantity
    # Accepted so a cart line round-trips; never read when pricing a quote.
    display_price_minor: Money | None = None


class QuoteRequest(WireModel):
    cart_id: UUIDText
    cart_version: Count
    lines: Annotated[list[QuoteRequestLine], Field(min_length=1, max_length=20)]

    @model_validator(mode="after")
    def unique_lines(self):
        if len({line.sku for line in self.lines}) != len(self.lines):
            raise ValueError("quote lines must have unique SKUs")
        return self


class QuoteLine(WireModel):
    sku: Sku
    quantity: Quantity
    unit_price_minor: UnitPrice
    line_total_minor: Money
    catalog_version: CatalogVersion


class Quote(WireModel):
    quote_id: UUIDText
    user_id: Identifier
    cart_id: UUIDText
    cart_version: Count
    lines: Annotated[list[QuoteLine], Field(min_length=1, max_length=20)]
    total_amount_minor: Money
    currency: Currency
    created_at: UTCTime
    expires_at: UTCTime


class PriceUpdateRequest(WireModel):
    price_minor: UnitPrice
    expected_catalog_version: CatalogVersion


class FacetRoot(WireModel):
    id: str
    label: str


class FacetBrand(WireModel):
    key: str
    label: str


class FacetDictionary(WireModel):
    dataset_revision: str
    dictionary_version: str
    roots: list[FacetRoot]
    path_prefixes: list[list[str]]
    brands: list[FacetBrand]
    colours: list[str]
    materials: list[str]
    allowed_apparel_sizes: list[str]
    observed_apparel_sizes: list[str]
    coverage_by_category: dict[str, dict[str, int]]


class SkuEntry(WireModel):
    sku: Sku
    product_id: Sku
    source_pid: str
    source_observation_id: str


class SkuManifest(WireModel):
    schema_version: Literal[1] = 1
    dataset_revision: str
    source_sha256: Sha256
    rules_version: str
    namespace: str
    sku_count: Count
    sorted_skus: list[SkuEntry]
    canonical_business_digest: Sha256
    content_sha256: Sha256 | None = None


class SourceManifest(WireModel):
    source_path: str
    raw_archive_descriptor: FileDescriptor
    source_sha256: Sha256
    byte_size: Count
    row_count: Count
    columns: list[str]
    acquired_at: UTCTime
    source_origin: Literal["user_upload"] = "user_upload"
    original_url: str | None = None
    licence: str | None = None
    rules_version: str
    dictionary_sha256: Sha256
    dataset_revision: str


class NormalizedFiles(WireModel):
    observations: FileDescriptor
    catalog: FileDescriptor
    dispositions: FileDescriptor
    issues: FileDescriptor


class NormalizedCatalogManifest(WireModel):
    schema_version: Literal[1] = 1
    source_manifest_ref: str
    dataset_revision: str
    rules_version: str
    dictionary_sha256: Sha256
    files: NormalizedFiles
    raw_rows: Count
    canonical_rows: Count
    active_rows: Count
    inactive_rows: Count
    superseded_rows: Count
    rejected_rows: Count
    canonical_business_digest: Sha256
    content_sha256: Sha256 | None = None


class CatalogProfile(WireModel):
    source_sha256: Sha256
    raw_rows: Count
    column_profiles: dict[str, dict[str, int]]
    nested_shape_counts: dict[str, int]
    identity_counts: dict[str, int]
    category_counts: dict[str, int]
    facet_coverage: dict[str, int]
    selected_counts: dict[str, int]
    issue_counts: dict[str, int]


class CatalogLoadReport(WireModel):
    import_id: UUIDText
    source_hash: Sha256
    dataset_revision: str
    raw_rows: Count
    canonical_rows: Count
    active_rows: Count
    inactive_rows: Count
    superseded_rows: Count
    rejected_rows: Count
    issue_counts: dict[str, int]
    inserted: Count
    updated: Count
    unchanged: Count
    load_mode: Literal["row", "copy"]
    chunk_count: Count
    chunks_resumed: Count = 0
    elapsed_by_stage_ms: dict[str, float]
    canonical_business_digest: Sha256
    status: Literal["promoted", "noop"]
    artifact_paths: list[str]


class EmbeddingManifest(WireModel):
    model_id: str
    revision: str
    dimensions: Literal[384]
    normalized: Literal[True]
    distance: Literal["cosine"]
    text_template_version: str
    input_hash: Sha256
    output_hash: Sha256
    row_count: Count
    encoded_rows: Count
    truncated_documents: Count
    batch_size: Count
    encode_seconds: Annotated[float, Field(ge=0)]


class ProjectionResult(WireModel):
    event_id: UUIDText
    outcome: Literal["applied", "duplicate", "stale", "conflict", "deferred"]
    previous_version: Count | None
    current_version: Count | None
    observed_commit_at: UTCTime | None
