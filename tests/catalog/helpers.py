"""Synthetic CSV rows and stock events for catalogue tests; never the real catalogue."""

import csv

from pipelines.catalog.normalize import load_dictionary

HEADER = load_dictionary()["source_header"]


def spec(**pairs):
    entries = ", ".join(f'{{"key"=>"{k}", "value"=>"{v}"}}' for k, v in pairs.items())
    return '{"product_specification"=>[' + entries + "]}"


def row(pid, **overrides):
    base = {
        "uniq_id": "obs-" + pid,
        "crawl_timestamp": "2016-01-01T00:00:00Z",
        "product_url": "https://example.invalid/synthetic",
        "product_name": f"Synthetic listing {pid}",
        "product_category_tree": '["Clothing >> Shirts >> Formal"]',
        "pid": pid,
        "retail_price": "999",
        "discounted_price": "379",
        "image": "[]",
        "is_FK_Advantage_product": "false",
        "description": "Synthetic catalogue fixture",
        "product_rating": "No rating available",
        "overall_rating": "No rating available",
        "brand": "",
        "product_specifications": "",
    }
    return {**base, **overrides}


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)
    return path
