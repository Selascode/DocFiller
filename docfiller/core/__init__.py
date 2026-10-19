"""Cœur métier de DocFiller (indépendant de l'interface graphique)."""

from docfiller.core.data_store import DataStore, normalize_key
from docfiller.core.exceptions import (
    DataCorruptedError,
    DataStoreError,
    DocFillerError,
    InvalidKeyError,
)

__all__ = [
    "DataStore",
    "normalize_key",
    "DocFillerError",
    "DataStoreError",
    "DataCorruptedError",
    "InvalidKeyError",
]
