"""Conservative product nouns resolved against recorded whole taxonomy segments.

Descriptions mentioning a shirt do not make trousers or bras shirts. This is
candidate relevance, applied alongside (never instead of) existing hard filters.
"""

import re

TYPES = (
    (r"\bbras?\b", ("bras",)),
    (r"\bt[ -]?shirts?\b|\btees?\b", ("t-shirts", "t shirts", "tshirts")),
    (r"\bshirts?\b", ("shirts", "formal shirts", "casual shirts")),
    (r"\btrousers?\b|\bpants\b|\bchinos\b", ("trousers", "pants", "chinos")),
)


def restrict_product_type(where, parameters, text):
    segments = next((values for pattern, values in TYPES if re.search(pattern, text, re.I)), None)
    if segments is None:
        return where, parameters
    return (
        where + " AND p.category_path_folded && %(product_type_segments)s::text[]",
        {**parameters, "product_type_segments": list(segments)},
    )
