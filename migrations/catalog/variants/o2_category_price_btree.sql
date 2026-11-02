-- O2 only: the single optional index under test (evaluation spec §3). Never a base migration.
CREATE INDEX IF NOT EXISTS products_o2_category_price ON products (namespace, category, price_minor);
ANALYZE products;
