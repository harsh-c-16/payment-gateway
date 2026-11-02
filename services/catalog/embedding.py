"""Local sentence encoder over the locked model files. No download or model choice at runtime.

numpy, onnxruntime and tokenizers are the optional `embeddings` dependency group, so these imports
stay inside the class: a deployment without the group still serves lexical search.
"""

import hashlib
import json
import os
from pathlib import Path

LOCK = Path(__file__).resolve().parents[2] / "contracts/data/catalog/embedding_model.lock.json"


def load_lock():
    return json.loads(LOCK.read_text(encoding="utf-8"))


def verify_model_files(directory, lock):
    """Refuses a model whose bytes differ from the lock instead of embedding with it."""
    for name, entry in lock["files"].items():
        data = (Path(directory) / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"model file {name} differs from the lock")


class Encoder:
    def __init__(self, directory):
        import numpy
        import onnxruntime
        from tokenizers import Tokenizer

        self.lock = load_lock()
        verify_model_files(directory, self.lock)
        self.numpy = numpy
        self.revision = self.lock["revision"]
        self.max_tokens = self.lock["max_tokens"]
        self.tokenizer = Tokenizer.from_file(str(Path(directory) / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=self.max_tokens)
        self.tokenizer.enable_padding()
        self.session = onnxruntime.InferenceSession(
            str(Path(directory) / "model.onnx"), providers=["CPUExecutionProvider"]
        )
        self.inputs = {item.name for item in self.session.get_inputs()}

    def encode(self, texts):
        """Returns (normalized float32 array, how many texts were cut at the token limit)."""
        numpy = self.numpy
        batch = self.tokenizer.encode_batch(list(texts))
        ids = numpy.array([item.ids for item in batch], dtype=numpy.int64)
        mask = numpy.array([item.attention_mask for item in batch], dtype=numpy.int64)
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.inputs:
            feeds["token_type_ids"] = numpy.zeros_like(ids)
        hidden = self.session.run(None, feeds)[0]
        weights = mask[:, :, None].astype(numpy.float32)
        pooled = (hidden * weights).sum(axis=1) / numpy.clip(weights.sum(axis=1), 1e-9, None)
        vectors = pooled / numpy.clip(numpy.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
        truncated = sum(len(item.overflowing) > 0 for item in batch)
        return vectors.astype(numpy.float32), truncated


def vector_text(vector):
    """pgvector's text format at fixed precision, so stored output hashes are reproducible."""
    return "[" + ",".join(f"{float(value):.7f}" for value in vector) + "]"


def encoder_from_environment():
    """Prewarmed once per worker when configured; otherwise vector modes report unavailable."""
    directory = os.environ.get("EMBEDDING_MODEL_DIR")
    if not directory:
        return None
    encoder = Encoder(directory)
    encoder.encode(["warmup"])
    return encoder
