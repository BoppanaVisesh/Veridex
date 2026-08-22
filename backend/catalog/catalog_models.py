"""
Catalog Intelligence — Data Models (§Catalog)

Data contracts and schemas for catalog ingestion, product field validation,
and evidence extraction. Follows the Pydantic ORM/contract patterns from backend/models.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────

class RawSourceType(str, Enum):
    CSV = "csv"
    HTML = "html"
    PDF = "pdf"
    MANUAL = "manual"


class ProductStatus(str, Enum):
    INGESTED = "ingested"
    CLEANING = "cleaning"
    VALIDATING = "validating"
    ENRICHING = "enriching"
    READY = "ready"
    NEEDS_REVIEW = "needs_review"


class FieldStatus(str, Enum):
    MISSING = "missing"
    RAW = "raw"
    VALIDATED = "validated"
    ENRICHED = "enriched"
    INFERRED = "inferred"
    NEEDS_REVIEW = "needs_review"
    VERIFIED = "verified"
    CONFLICTED = "conflicted"
    FLAGGED = "flagged"


class EnrichmentMethod(str, Enum):
    SOURCE_DATA = "source_data"
    LLM = "llm"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"
    NO_EVIDENCE = "no_evidence"


# ── Models ─────────────────────────────────────────────────────────────────────

class Product(BaseModel):
    """Catalog product item."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    raw_source_type: RawSourceType
    status: ProductStatus = ProductStatus.INGESTED
    canonical_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ProductField(BaseModel):
    """Field attribute belonging to a product."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    product_id: str
    field_name: str
    value: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: FieldStatus = FieldStatus.MISSING
    unit: Optional[str] = None
    enrichment_method: Optional[EnrichmentMethod] = None
    is_verified: bool = False
    source_fields: Optional[str] = None
    validation_reason: Optional[str] = None
    reasoning: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class FieldEvidence(BaseModel):
    """Raw evidence supporting an extracted or validated product field."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    product_field_id: str
    source_label: str
    raw_value: str
    extracted_at: datetime = Field(default_factory=datetime.utcnow)

