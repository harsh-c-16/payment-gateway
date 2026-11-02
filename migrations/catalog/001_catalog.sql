-- M2 catalogue, import ledger and staging. All keys are namespace-scoped; no outbox DDL here:
-- that table comes from Aditya's library and the diagnostics template is added with H04.
CREATE TABLE catalog_imports (
    import_id uuid PRIMARY KEY,
    namespace varchar(62) NOT NULL,
    source_hash char(64) NOT NULL,
    rules_version varchar(32) NOT NULL,
    dictionary_sha256 char(64) NOT NULL,
    dataset_revision varchar(64) NOT NULL,
    canonical_business_digest char(64) NOT NULL,
    canonical_rows integer NOT NULL CHECK (canonical_rows >= 0),
    chunk_rows integer NOT NULL CHECK (chunk_rows > 0),
    load_mode varchar(8) NOT NULL CHECK (load_mode IN ('row', 'copy')),
    status varchar(16) NOT NULL CHECK (status IN ('staging', 'complete')),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    UNIQUE (namespace, source_hash, rules_version)
);

CREATE TABLE catalog_import_chunks (
    import_id uuid NOT NULL REFERENCES catalog_imports,
    chunk_no integer NOT NULL,
    row_count integer NOT NULL CHECK (row_count > 0),
    chunk_sha256 char(64) NOT NULL,
    load_mode varchar(8) NOT NULL CHECK (load_mode IN ('row', 'copy')),
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (import_id, chunk_no)
);

-- Same columns for row and COPY loads; only the statement issued differs (I0 versus I1).
CREATE TABLE catalog_stage (
    import_id uuid NOT NULL REFERENCES catalog_imports,
    source_row integer NOT NULL,
    sku varchar(64) NOT NULL,
    product_id varchar(64) NOT NULL,
    source_pid varchar(61) NOT NULL,
    source_observation_id varchar(128) NOT NULL,
    source_crawled_at timestamptz NOT NULL,
    source_url text NOT NULL,
    title text NOT NULL,
    description text,
    category varchar(64),
    category_path text[] NOT NULL,
    category_path_raw text NOT NULL,
    brand text,
    brand_normalized text,
    size varchar(16),
    size_kind varchar(16),
    colour text,
    material text,
    seller_id text,
    price_minor bigint CHECK (price_minor BETWEEN 1 AND 1000000000),
    retail_price_minor bigint CHECK (retail_price_minor BETWEEN 1 AND 1000000000),
    rating varchar(8),
    is_fk_advantage boolean,
    image_urls jsonb NOT NULL,
    attributes jsonb NOT NULL,
    unkeyed_specifications jsonb NOT NULL,
    specification_entries jsonb NOT NULL,
    quality_flags text[] NOT NULL,
    active boolean NOT NULL,
    inactive_reason varchar(32),
    normalized_business_hash char(64) NOT NULL,
    PRIMARY KEY (import_id, source_row),
    UNIQUE (import_id, sku)
);

CREATE TABLE products (
    namespace varchar(62) NOT NULL,
    sku varchar(64) NOT NULL,
    product_id varchar(64) NOT NULL,
    dataset_revision varchar(64) NOT NULL,
    import_id uuid NOT NULL REFERENCES catalog_imports,
    source_row integer NOT NULL,
    source_pid varchar(61) NOT NULL,
    source_observation_id varchar(128) NOT NULL,
    source_crawled_at timestamptz NOT NULL,
    source_url text NOT NULL,
    title text NOT NULL,
    description text,
    category varchar(64),
    category_path text[] NOT NULL,
    category_path_folded text[] NOT NULL,
    category_path_raw text NOT NULL,
    brand text,
    brand_normalized text,
    size varchar(16),
    size_kind varchar(16),
    colour text,
    material text,
    seller_id text,
    price_minor bigint CHECK (price_minor BETWEEN 1 AND 1000000000),
    retail_price_minor bigint CHECK (retail_price_minor BETWEEN 1 AND 1000000000),
    currency char(3) NOT NULL DEFAULT 'INR' CHECK (currency = 'INR'),
    currency_source varchar(32) NOT NULL DEFAULT 'project_assumption',
    rating varchar(8),
    is_fk_advantage boolean,
    image_urls jsonb NOT NULL,
    attributes jsonb NOT NULL,
    unkeyed_specifications jsonb NOT NULL,
    specification_entries jsonb NOT NULL,
    quality_flags text[] NOT NULL,
    catalog_version bigint NOT NULL DEFAULT 1 CHECK (catalog_version >= 1),
    active boolean NOT NULL,
    inactive_reason varchar(32),
    normalized_business_hash char(64) NOT NULL,
    -- Precomputed once at promotion so lexical ranking never re-parses text per request.
    -- A plain column, not an index: B0 and O2 both scan it. A GIN index is out of scope (§10).
    search_vector tsvector NOT NULL,
    PRIMARY KEY (namespace, sku),
    CHECK (NOT active OR (price_minor IS NOT NULL AND inactive_reason IS NULL)),
    CHECK (active OR inactive_reason IS NOT NULL)
);

CREATE TABLE source_observations (
    namespace varchar(62) NOT NULL,
    source_hash char(64) NOT NULL,
    row_no integer NOT NULL,
    uniq_id text NOT NULL,
    pid text NOT NULL,
    raw_sha256 char(64) NOT NULL,
    mandatory_valid boolean NOT NULL,
    PRIMARY KEY (namespace, source_hash, row_no)
);

CREATE TABLE source_dispositions (
    namespace varchar(62) NOT NULL,
    source_hash char(64) NOT NULL,
    row_no integer NOT NULL,
    disposition varchar(40) NOT NULL CHECK (disposition IN (
        'canonical_active', 'canonical_inactive_missing_price', 'superseded', 'rejected_mandatory'
    )),
    issue_codes text[] NOT NULL,
    PRIMARY KEY (namespace, source_hash, row_no)
);

CREATE TABLE facet_dictionaries (
    namespace varchar(62) NOT NULL,
    dataset_revision varchar(64) NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY (namespace, dataset_revision)
);
