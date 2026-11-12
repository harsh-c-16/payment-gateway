-- Presentation-only eligibility reads; never apply this variant to an evaluation baseline.
CREATE INDEX IF NOT EXISTS products_prototype_eligible
    ON products (namespace, sku) INCLUDE (category, price_minor, colour) WHERE active;
ANALYZE products;
