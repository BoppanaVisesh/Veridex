"""
Catalog Intelligence — Field Validation Module (§Catalog)

Validates product fields for:
1. Plausibility (data types, format checks, controlled vocabularies, unit requirements)
2. Cross-field consistency (material vs weight vs dimensions)
3. Cross-source contradictions (flagging conflicting raw values from multiple evidence sources)

Updates the database with validation_reason so explanations have full audit trail.
"""

from __future__ import annotations

import re
from typing import Any

from backend.catalog.catalog_models import FieldStatus
from backend.catalog.catalog_database import catalog_db


CONTROLLED_CATEGORIES = {
    "industrial pumps", "generators", "solar equipment", "motors & drives",
    "valves & fittings", "electrical", "tools", "hardware", "fasteners", "safety"
}

MEASURABLE_FIELDS = {"weight", "voltage", "power", "dimensions", "length", "width", "height", "temperature"}

AMBIGUOUS_PATTERNS = re.compile(
    r'\b(varies|unknown|n/a|tbd|approx|to be determined|contact us|see spec|refer to manual)\b',
    re.IGNORECASE
)


def validate_field(
    product: dict[str, Any],
    field: dict[str, Any],
    all_fields_for_product: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Validate a single ProductField dict against evidence and other product fields.
    Returns dict: {status: FieldStatus, confidence: float, reason: str}
    """
    f_name = field.get("field_name", "").lower()
    val = field.get("value")
    unit = field.get("unit")
    current_status = field.get("status", FieldStatus.RAW)
    evidence = field.get("evidence", [])

    reasons = []

    # ── 1. Cross-Source Contradiction Check ─────────────────────────────
    if len(evidence) >= 2:
        distinct_raws = {e.get("raw_value", "").strip().lower() for e in evidence if e.get("raw_value")}
        distinct_sources = {e.get("source_label", "").strip() for e in evidence}
        if len(distinct_raws) > 1 and len(distinct_sources) > 1:
            raw_list_str = " vs ".join(f"'{r}'" for r in list(distinct_raws)[:3])
            return {
                "status": FieldStatus.CONFLICTED,
                "confidence": 0.35,
                "reason": f"Cross-source contradiction: evidence sources disagree ({raw_list_str})."
            }

    # ── 2. Flagged-during-cleaning passthrough ──────────────────────────
    if current_status == FieldStatus.FLAGGED or field.get("confidence", 0.8) <= 0.4:
        return {
            "status": FieldStatus.FLAGGED,
            "confidence": 0.40,
            "reason": f"Flagged during ingestion: value '{val}' is ambiguous or unparseable."
        }

    # ── 3. Empty/Missing ─────────────────────────────────────────────────
    if val is None or str(val).strip() == "":
        return {
            "status": FieldStatus.MISSING,
            "confidence": 0.0,
            "reason": f"Field '{f_name}' is empty or missing."
        }

    val_str = str(val).strip()

    # ── 4. Ambiguous text patterns ───────────────────────────────────────
    if AMBIGUOUS_PATTERNS.search(val_str):
        return {
            "status": FieldStatus.FLAGGED,
            "confidence": 0.30,
            "reason": f"Value '{val_str}' contains ambiguous/placeholder text for field '{f_name}'."
        }

    # ── 5. Numeric plausibility for numeric fields ───────────────────────
    if f_name in ("weight", "voltage", "power", "price", "current", "frequency"):
        try:
            float_val = float(val_str.replace(',', ''))
            if float_val < 0:
                return {
                    "status": FieldStatus.FLAGGED,
                    "confidence": 0.20,
                    "reason": (
                        f"Negative physical quantity: value '{val_str}' is invalid for field '{f_name}'. "
                        f"Physical measurements cannot be negative."
                    )
                }
            if f_name == "weight" and float_val == 0:
                reasons.append(f"Weight value is exactly zero — likely a data entry error.")
            if f_name == "voltage" and float_val > 50000:
                reasons.append(f"Voltage {float_val}V exceeds plausible industrial range (>50kV).")
        except ValueError:
            return {
                "status": FieldStatus.FLAGGED,
                "confidence": 0.45,
                "reason": f"Value '{val_str}' is non-numeric for numeric field '{f_name}'."
            }

    # ── 6. Unit check for measurable fields ─────────────────────────────
    if f_name in MEASURABLE_FIELDS and f_name != "dimensions":
        if not unit:
            reasons.append(f"Missing measurement unit for field '{f_name}' (value: '{val_str}').")

    # ── 7. Controlled category vocabulary ───────────────────────────────
    if f_name == "category" and val_str.strip().lower() not in CONTROLLED_CATEGORIES:
        reasons.append(
            f"Category '{val_str}' is not in the standardized taxonomy "
            f"({', '.join(sorted(CONTROLLED_CATEGORIES))})."
        )

    # ── 8. Cross-Field Consistency ───────────────────────────────────────
    all_fields_map = {f.get("field_name", "").lower(): f for f in all_fields_for_product}

    # Weight vs material vs dimensions plausibility
    if f_name == "weight" and val:
        try:
            w_val = float(str(val).replace(',', ''))
            mat_field = all_fields_map.get("material", {}).get("value", "").lower()
            dim_field = all_fields_map.get("dimensions", {}).get("value", "").lower()

            if (("steel" in mat_field or "iron" in mat_field) and w_val < 0.05):
                if dim_field and any(int(num) > 300 for num in re.findall(r'\d+', dim_field)):
                    reasons.append(
                        f"Weight {w_val} {unit or ''} is implausibly low for a steel/iron item "
                        f"with dimensions '{dim_field}'."
                    )
        except (ValueError, TypeError):
            pass

    # ── Compile result ────────────────────────────────────────────────────
    if reasons:
        return {
            "status": FieldStatus.FLAGGED,
            "confidence": 0.55,
            "reason": "Validation warning: " + "; ".join(reasons)
        }

    return {
        "status": FieldStatus.VALIDATED,
        "confidence": 0.90,
        "reason": f"Field '{f_name}' passed plausibility, type, and cross-field consistency validation."
    }


def validate_all_product_fields(product_id: str) -> dict[str, Any]:
    """
    Runs validate_field for all fields of a product and updates ProductField rows in DB.
    Stores validation_reason for audit trail.
    Returns summary stats with field-level detail.
    """
    product = catalog_db.get_product_with_details(product_id)
    if not product:
        raise ValueError(f"Product '{product_id}' not found.")

    fields = product.get("fields", [])
    validated_count = 0
    conflicted_count = 0
    flagged_count = 0
    field_results = []

    for f in fields:
        f_status = (f.get("status") or "").lower()
        # Skip inferred/enriched/needs_review fields created during enrichment pass
        if f_status in (FieldStatus.ENRICHED.value, FieldStatus.INFERRED.value, FieldStatus.NEEDS_REVIEW.value):
            field_results.append({
                "field": f.get("field_name"),
                "status": f_status,
                "reason": "Enriched / Inferred field — preserved from enrichment pass."
            })
            continue

        res = validate_field(product, f, fields)
        new_status: FieldStatus = res["status"]
        new_confidence: float = res["confidence"]
        reason: str = res["reason"]

        if new_status == FieldStatus.VALIDATED:
            validated_count += 1
        elif new_status == FieldStatus.CONFLICTED:
            conflicted_count += 1
        elif new_status == FieldStatus.FLAGGED:
            flagged_count += 1

        # Persist to DB using the clean update method
        catalog_db.update_product_field_validation(f["id"], new_status, new_confidence, reason)

        field_results.append({
            "field": f.get("field_name"),
            "status": new_status.value,
            "confidence": new_confidence,
            "reason": reason
        })

    return {
        "validated_count": validated_count,
        "conflicted_count": conflicted_count,
        "flagged_count": flagged_count,
        "field_results": field_results,
    }
