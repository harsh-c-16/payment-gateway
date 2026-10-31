"""M04 capture interface; sink processing and offset eligibility follow in M05."""

from .bronze import BronzeCapture, CaptureTooLarge, SourceCorruption, ingest_bronze, read_bronze

__all__ = ["BronzeCapture", "CaptureTooLarge", "SourceCorruption", "ingest_bronze", "read_bronze"]
