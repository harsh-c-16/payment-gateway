"""Offline embeddings with the real locked model: determinism, text rules and re-embed policy."""

from uuid import uuid4

import psycopg
import pytest

from pipelines.catalog.embeddings import build_embeddings, embedding_text
from services.catalog.embedding import load_lock, verify_model_files
from tests.catalog.helpers import import_rows, row, spec


def base(**overrides):
    return {
        "title": "Blue shirt",
        "category": "clothing",
        "category_path": ["Clothing", "Shirts"],
        "brand": "Acme",
        "material": "cotton",
        "colour": "blue",
        "attributes": {"occasion": ["Casual", "Casual"]},
        "description": "Soft shirt Price: Rs. 1,299 width 40 cm",
        **overrides,
    }


def test_template_has_fixed_order_and_strips_only_price_fragments():
    text = embedding_text(base())
    assert text == (
        "Blue shirt | Clothing > Shirts | Acme | cotton | blue | Casual | Soft shirt width 40 cm"
    )
    assert "1,299" not in text and "40 cm" in text


def test_template_handles_inr_and_decimal_and_skips_unknown_fields():
    text = embedding_text(
        base(
            category=None,
            brand=None,
            material=None,
            colour=None,
            attributes={},
            description="Nice Price: INR 45.50 mat",
        )
    )
    assert text == "Blue shirt | Nice mat"


def test_unknown_category_path_is_not_embedded_as_a_department():
    assert "Mystery" not in embedding_text(base(category=None, category_path=["Mystery title"]))


def test_vectors_are_normalized_384_deterministic_and_meaningful(encoder):
    numpy = encoder.numpy
    vectors, truncated = encoder.encode(
        ["red cotton shirt", "red cotton shirt", "cotton shirt in red", "steel water bottle"]
    )
    assert vectors.shape == (4, 384) and truncated == 0
    assert numpy.allclose(numpy.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)
    assert numpy.array_equal(vectors[0], vectors[1])
    assert vectors[0] @ vectors[2] > vectors[0] @ vectors[3] + 0.2


def test_long_text_is_cut_at_the_locked_token_limit(encoder):
    _, truncated = encoder.encode(["word " * 400])
    assert truncated == 1


def test_changed_model_bytes_are_refused(tmp_path):
    lock = load_lock()
    for name in lock["files"]:
        (tmp_path / name).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="differs from the lock"):
        verify_model_files(tmp_path, lock)


def test_build_is_repeatable_and_price_change_does_not_re_embed(tmp_path, database_url, encoder):
    namespace = "bench-h-" + uuid4().hex[:16]
    rows = [
        row("A1", product_name="Blue cotton shirt", product_specifications=spec(Color="Blue")),
        row("A2", product_name="Steel watch", discounted_price=""),
    ]
    import_rows(tmp_path, database_url, namespace, rows)
    with psycopg.connect(database_url, autocommit=True) as connection:
        first = build_embeddings(connection, namespace, encoder, out=tmp_path / "embed")
        assert (first.row_count, first.encoded_rows) == (2, 2)
        assert (tmp_path / "embed/embedding_manifest.json").is_file()
        second = build_embeddings(connection, namespace, encoder)
        assert second.encoded_rows == 0
        assert (second.input_hash, second.output_hash) == (first.input_hash, first.output_hash)
        connection.execute(
            "UPDATE products SET embedding=NULL WHERE namespace=%s AND sku='FK-A1'", (namespace,)
        )
        repaired = build_embeddings(connection, namespace, encoder)
        assert repaired.encoded_rows == 1 and repaired.output_hash == first.output_hash
        connection.execute(
            "UPDATE products SET price_minor=999999,catalog_version=catalog_version+1 "
            "WHERE namespace=%s AND sku='FK-A1'",
            (namespace,),
        )
        priced = build_embeddings(connection, namespace, encoder)
        assert priced.encoded_rows == 0 and priced.output_hash == first.output_hash
        connection.execute(
            "UPDATE products SET title='A different title' WHERE namespace=%s AND sku='FK-A1'",
            (namespace,),
        )
        retitled = build_embeddings(connection, namespace, encoder)
        assert retitled.encoded_rows == 1 and retitled.output_hash != first.output_hash
        count = connection.execute(
            "SELECT count(*) FROM products WHERE namespace=%s AND vector_dims(embedding)=384",
            (namespace,),
        ).fetchone()[0]
    assert count == 2
