-- Optional semantic branch. catalog_db already has the vector extension from infra. No ANN index
-- here: HNSW is a separate variant, so an exact baseline can never use one by accident.
ALTER TABLE products
    ADD COLUMN embedding vector(384),
    ADD COLUMN embedding_revision varchar(64),
    ADD COLUMN embedding_text_hash char(64);
