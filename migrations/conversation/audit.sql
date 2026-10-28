-- Read-only, namespace-scoped reconciliation. Bind %(namespace)s explicitly.
SELECT c.cart_id, c.session_id, c.user_id, c.version, c.updated_at,
       count(i.sku) AS unique_lines, coalesce(sum(i.quantity), 0) AS units
FROM carts c LEFT JOIN cart_items i USING (namespace, cart_id)
WHERE c.namespace = %(namespace)s
GROUP BY c.namespace, c.cart_id;

SELECT operation, count(*) AS retained_keys
FROM operation_keys WHERE namespace = %(namespace)s GROUP BY operation;

SELECT request_id, turn_id, session_id, request_hash, created_at
FROM turns WHERE namespace = %(namespace)s ORDER BY created_at, request_id;
