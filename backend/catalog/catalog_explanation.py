"""
Catalog Intelligence — Human-Readable Explanation Engine (§Catalog)

Produces structured, audit-ready explanations for product field values,
detailing evidence sources, confidence scores, validation rationale, and human verification needs.

Clearly distinguishes:
  - SOURCE VERIFIED: value extracted directly from reliable source data (100% confidence, verified)
  - SOURCE VALIDATED: value provided in upload and passed cross-field validation
  - LLM EXTRACTED: value extracted by LLM from descriptive text with high confidence
  - LLM INFERRED: value deduced by LLM reasoning over contextual evidence
  - RULE INFERRED: value inferred by deterministic pattern matcher
  - NEEDS REVIEW / UNKNOWN: value lacks reliable supporting evidence
"""

from __future__ import annotations

from typing import Any


def _source_provenance_label(source_label: str) -> str:
    """Human-readable label for an evidence source_label."""
    if source_label in ("llm", "ai_inferred"):
        return "🤖 LLM Intelligence (Gemini)"
    elif source_label == "deterministic_fallback":
        return "🔧 Deterministic Rule Engine"
    elif source_label == "source_data":
        return "📄 Direct Source Extraction"
    elif source_label == "no_evidence":
        return "⚠️ No Supporting Evidence"
    else:
        return f"📄 Source: {source_label}"


def explain_field(
    field: dict[str, Any],
    evidence_list: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Build a comprehensive explanation for a single ProductField and its evidence trail.
    Clearly explains what value was produced, whether it was extracted, LLM-inferred,
    or rule-inferred, which source fields were used, confidence grade, and human verification status.
    """
    f_name = field.get("field_name", "unknown")
    val = field.get("value", "")
    unit = field.get("unit")
    status = (field.get("status") or "raw").lower()
    conf = field.get("confidence")
    validation_reason = field.get("validation_reason")
    reasoning = field.get("reasoning")
    enrichment_method = field.get("enrichment_method") or "unknown"
    is_verified = bool(field.get("is_verified", False))
    source_fields = field.get("source_fields")

    val_str = f"{val} {unit}".strip() if unit else str(val)
    conf_pct = f"{conf:.0%}" if conf is not None else "—"

    # Human Verification Recommendation
    if is_verified or status in ("verified", "validated"):
        human_review_rec = "✅ **Human Verification Not Required** — Directly supported by authentic source data."
        human_review_badge = "VERIFIED"
    elif status in ("needs_review", "flagged", "conflicted") or val == "Unknown" or (conf is not None and conf < 0.50):
        human_review_rec = "🚨 **Human Verification Required** — Inadequate or conflicting source evidence."
        human_review_badge = "ACTION REQUIRED"
    else:
        human_review_rec = "⚠️ **Human Verification Recommended** — Inferred specification, not explicitly confirmed in source."
        human_review_badge = "RECOMMENDED"

    # Detailed Provenance Description
    if status == "verified" or is_verified:
        provenance = "Source Provided → Validated & Verified"
        method_desc = "Direct Source Data"
    elif status == "validated":
        provenance = "Source Provided → Cleaned → Validated"
        method_desc = "Source Data (Validated)"
    elif enrichment_method in ("llm", "ai_inferred"):
        provenance = "LLM Extracted/Inferred from Context"
        method_desc = "Gemini LLM Inference"
    elif enrichment_method == "deterministic_fallback":
        provenance = "Deterministic Rule Engine Inference (No LLM)"
        method_desc = "Rule Pattern Matching"
    elif enrichment_method == "no_evidence" or val == "Unknown":
        provenance = "No Reliable Evidence Found"
        method_desc = "Unsupported / Missing Evidence"
    elif status in ("flagged", "conflicted"):
        provenance = "Source Provided → Failed Validation Checks"
        method_desc = "Source Data (Flagged)"
    else:
        provenance = "Source Provided → Cleaned (Awaiting Validation)"
        method_desc = "Raw Ingestion"

    # Confidence Quality Grade
    if conf is not None:
        if conf >= 0.90:
            conf_grade = "High Confidence (Direct Source Evidence)"
            conf_icon = "🟢"
        elif conf >= 0.70:
            conf_grade = "Strong Evidence (Strong Contextual Support)"
            conf_icon = "🟢"
        elif conf >= 0.50:
            conf_grade = "Moderate (Probable Inference — Verification Advised)"
            conf_icon = "🟡"
        else:
            conf_grade = "Low / Insufficient Evidence"
            conf_icon = "🔴"
    else:
        conf_grade = "Unrated"
        conf_icon = "⚪"

    parts = [
        f"## Field: {f_name.replace('_', ' ').capitalize()}",
        f"",
        f"**Value:** `{val_str}`",
        f"**Method:** {method_desc}",
        f"**Provenance:** {provenance}",
        f"**Status:** `{status.upper()}` {conf_icon}",
        f"**Confidence:** {conf_pct} ({conf_grade})",
        f"",
    ]

    if source_fields:
        parts.append(f"**Source Fields Used:** `{source_fields}`")
        parts.append("")

    # Status explanation
    if status == "verified" or is_verified:
        parts.append("### ✓ Verified Field Status")
        parts.append("This value is directly extracted from reliable source documentation and passed all plausibility checks.")
    elif status == "validated":
        parts.append("### ✓ Validation Passed")
        parts.append("Field value cleared plausibility, type format, and cross-field consistency validation.")
        if validation_reason:
            parts.append(f"*Validation note: {validation_reason}*")
    elif status == "conflicted":
        parts.append("### ⚠️ Source Conflict Detected")
        parts.append("Multiple evidence sources provided **conflicting raw values**. Manual human review is required to resolve.")
        if validation_reason:
            parts.append(f"*Conflict detail: {validation_reason}*")
    elif status == "flagged":
        parts.append("### 🚩 Validation Flagged")
        parts.append("Value is ambiguous, unparseable, or failed a physical measurement plausibility check.")
        if validation_reason:
            parts.append(f"*Flag reason: {validation_reason}*")
    elif status == "needs_review" or val == "Unknown":
        parts.append("### 🔍 Needs Review")
        parts.append(
            "The system refused to guess this specification because insufficient factual evidence was provided. "
            "Marketing buzzwords (e.g. 'heavy duty', 'industrial') are never treated as accredited certifications."
        )
    elif status == "inferred" or status == "enriched":
        parts.append("### 💡 Inferred Attribute")
        parts.append(
            "This value was **inferred** based on available context. It did NOT appear explicitly as a confirmed specification in the original source."
        )

    # Reasoning / Rationale
    if reasoning or validation_reason:
        parts.append("")
        parts.append("### 📋 System Reasoning")
        if reasoning:
            parts.append(f"> {reasoning}")
        elif validation_reason:
            parts.append(f"> {validation_reason}")

    # Evidence Trail
    parts.append("")
    parts.append("### 📜 Evidence Trail")
    if evidence_list:
        for ev in evidence_list:
            src = ev.get("source_label", "Unknown Source")
            raw = ev.get("raw_value", "")
            ext_at = ev.get("extracted_at", "")
            time_str = f" — {ext_at[:19]}" if ext_at else ""

            provenance_lbl = _source_provenance_label(src)
            parts.append(f"• **{provenance_lbl}**{time_str}")
            if src in ("llm", "ai_inferred", "deterministic_fallback", "no_evidence"):
                parts.append(f"  _Reasoning / Method:_ {raw}")
            else:
                parts.append(f"  _Raw value:_ `{raw}`")
    else:
        parts.append("No historical evidence rows attached.")

    # Human Review Callout Box
    parts.append("")
    parts.append(f"> **Human Checkpoint:** {human_review_rec}")

    explanation_md = "\n".join(parts)

    return {
        "field_name": f_name,
        "value": val,
        "unit": unit,
        "status": status,
        "confidence": conf,
        "enrichment_method": enrichment_method,
        "is_verified": is_verified,
        "source_fields": source_fields,
        "reasoning": reasoning,
        "provenance": provenance,
        "validation_reason": validation_reason,
        "human_review_rec": human_review_rec,
        "human_review_badge": human_review_badge,
        "explanation": explanation_md,
        "evidence": evidence_list,
    }
