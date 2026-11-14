"""Offline catalogue embeddings (common §10). Never runs during a request.

    EMBEDDING_MODEL_DIR=artifacts/models/all-MiniLM-L6-v2 \\
        python -m pipelines.catalog.embeddings --namespace bench-smoke --out DIR
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from time import perf_counter

import psycopg

from pipelines.catalog.artifacts import write_json
from services.catalog.embedding import Encoder, vector_text
from shared.contracts.catalog import EmbeddingManifest

# Removes the stale listing price some descriptions embed. Frozen and deliberately narrow:
# dimensions and other numbers stay.
PRICE_FRAGMENT = re.compile(r"Price:\s*(?:Rs\.?|INR)\s*[\d,]+(?:\.\d+)?")
SEPARATOR = " | "
BATCH_SIZE = 64


def embedding_text(row):
    """Template v2: fixed field order. Current price and stock are never part of the text."""
    attributes = row["attributes"] or {}
    occasion = sorted(set(attributes.get("occasion", [])))
    description = row["description"]
    fields = [
        row["title"],
        " > ".join(row["category_path"]) if row["category"] else None,
        row["brand"],
        row["material"],
        row["colour"],
        ", ".join(occasion) or None,
        " ".join(PRICE_FRAGMENT.sub(" ", description).split()) if description else None,
    ]
    return SEPARATOR.join(field for field in fields if field)


def text_hash(text, version):
    return hashlib.sha256(f"{version}\n{text}".encode()).hexdigest()


def build_embeddings(connection, namespace, encoder, *, out=None, batch_size=BATCH_SIZE):
    """Encodes only rows whose text, template or model changed, so a price change costs nothing."""
    lock = encoder.lock
    version = lock["text_template_version"]
    columns = (
        "sku,title,category,category_path,brand,material,colour,attributes,description,"
        "embedding_text_hash,embedding_revision,embedding IS NULL AS missing_embedding"
    )
    with connection.cursor(row_factory=psycopg.rows.dict_row) as cursor:
        rows = cursor.execute(
            f"SELECT {columns} FROM products WHERE namespace=%s ORDER BY sku", (namespace,)
        ).fetchall()
    pending, input_pairs = [], []
    for row in rows:
        text = embedding_text(row)
        digest = text_hash(text, version)
        input_pairs.append([row["sku"], digest])
        if (
            row["missing_embedding"]
            or row["embedding_text_hash"] != digest
            or row["embedding_revision"] != lock["revision"]
        ):
            pending.append((row["sku"], text, digest))
    # Sorting by length keeps padding, and therefore inference time, small within each batch.
    pending.sort(key=lambda item: (len(item[1]), item[0]))
    started = perf_counter()
    truncated = 0
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        vectors, cut = encoder.encode([item[1] for item in batch])
        truncated += cut
        with connection.transaction():
            connection.execute(
                "CREATE TEMP TABLE embedding_batch (sku text, embedding vector(384), "
                "text_hash char(64)) ON COMMIT DROP"
            )
            with connection.cursor().copy("COPY embedding_batch FROM STDIN") as copy:
                for (sku, _, digest), vector in zip(batch, vectors, strict=True):
                    copy.write_row((sku, vector_text(vector), digest))
            connection.execute(
                "UPDATE products p SET embedding=b.embedding,embedding_text_hash=b.text_hash,"
                "embedding_revision=%s FROM embedding_batch b WHERE p.namespace=%s AND p.sku=b.sku",
                (lock["revision"], namespace),
            )
    elapsed = perf_counter() - started
    stored = connection.execute(
        "SELECT sku,embedding::text FROM products WHERE namespace=%s ORDER BY sku", (namespace,)
    ).fetchall()
    manifest = EmbeddingManifest(
        model_id=lock["model_id"],
        revision=lock["revision"],
        dimensions=lock["dimensions"],
        normalized=lock["normalized"],
        distance=lock["distance"],
        text_template_version=version,
        input_hash=hashlib.sha256(json.dumps(input_pairs).encode()).hexdigest(),
        output_hash=hashlib.sha256(json.dumps([list(row) for row in stored]).encode()).hexdigest(),
        row_count=len(rows),
        encoded_rows=len(pending),
        truncated_documents=truncated,
        batch_size=batch_size,
        encode_seconds=elapsed,
    )
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        write_json(Path(out) / "embedding_manifest.json", manifest.model_dump(mode="json"))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    arguments = parser.parse_args()
    if not 1 <= arguments.batch_size <= BATCH_SIZE:
        parser.error("--batch-size must be between 1 and 64")
    encoder = Encoder(os.environ["EMBEDDING_MODEL_DIR"])
    with psycopg.connect(os.environ["CATALOG_DATABASE_URL"], autocommit=True) as connection:
        manifest = build_embeddings(
            connection,
            arguments.namespace,
            encoder,
            out=arguments.out,
            batch_size=arguments.batch_size,
        )
    print(json.dumps(manifest.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
