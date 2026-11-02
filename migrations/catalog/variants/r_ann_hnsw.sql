-- R-ANN only: evaluation spec §3 defaults for the first comparison.
CREATE INDEX IF NOT EXISTS products_r_ann_hnsw ON products
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
ANALYZE products;
