"""Cœur métier de DocFiller (indépendant de l'interface graphique)."""

from docfiller.core.data_store import DataStore, normalize_key
from docfiller.core.exceptions import (
    DataCorruptedError,
    DataStoreError,
    DocFillerError,
    InvalidKeyError,
    NoFormFieldsError,
    PdfCorruptedError,
    PdfEncryptedError,
    PdfError,
    PdfNotFoundError,
    PdfWriteError,
    ProcessingCancelled,
)
from docfiller.core.matcher import FieldMatcher, Match, MatchMethod
from docfiller.core.pdf_engine import FieldType, FillResult, FormField, PdfEngine
from docfiller.core.processor import Analysis, DocumentProcessor, MissingFieldResolver, Resolution

__all__ = [
    "DataStore",
    "normalize_key",
    "DocFillerError",
    "DataStoreError",
    "DataCorruptedError",
    "InvalidKeyError",
    "PdfError",
    "PdfNotFoundError",
    "PdfCorruptedError",
    "PdfEncryptedError",
    "PdfWriteError",
    "NoFormFieldsError",
    "ProcessingCancelled",
    "FieldType",
    "FormField",
    "FillResult",
    "PdfEngine",
    "FieldMatcher",
    "Match",
    "MatchMethod",
    "Analysis",
    "DocumentProcessor",
    "MissingFieldResolver",
    "Resolution",
]
