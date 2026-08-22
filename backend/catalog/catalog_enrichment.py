"""
Catalog Intelligence — AI & Rule-based Field Enrichment Module (§Catalog)

Evidence-Based, Trustworthy 3-Tier Enrichment Pipeline:

Level 1: SOURCE / EVIDENCE-BASED EXTRACTION
  - Extracts attributes explicitly present in uploaded product data, descriptions, specs, or model numbers.
  - Confidence: 90–100% (Directly supported by reliable source data).
  - Status: VERIFIED or VALIDATED.
  - Method: source_data.

Level 2: LLM-BASED ENRICHMENT (Gemini)
  - Used when GEMINI_API_KEY is configured.
  - Strict anti-hallucination prompt: Never fabricates certifications, dimensions, voltage, or weight.
  - Distinguishes "extracted" from "inferred".
  - Never claims an unsupported certification as fact.
  - Returns "Unknown" with NEEDS_REVIEW when evidence is insufficient.
  - Confidence: 70–89% (Extracted) or 50–69% (Inferred).
  - Method: llm.

Level 3: DETERMINISTIC RULE-BASED FALLBACK
  - Used when GEMINI_API_KEY is NOT set.
  - Category / Material inferred with confidence 50–65% (status: INFERRED).
  - Certifications: NEVER inferred from marketing terms ("industrial", "heavy duty", "premium", "professional").
    Produces value="Unknown", status=NEEDS_REVIEW, confidence=0.0, method=no_evidence.
  - Method: deterministic_fallback.
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

from backend.catalog.catalog_models import (
    ProductField, FieldEvidence, FieldStatus, EnrichmentMethod
)
from backend.catalog.catalog_database import catalog_db


EXPECTED_DEFAULT_FIELDS = [
    "name", "category", "material", "weight", "dimensions", "voltage", "certification"
]

# Marketing buzzwords that must NEVER trigger a certification inference
MARKETING_BUZZWORDS = re.compile(
    r'\b(industrial|heavy\s*duty|heavy-duty|premium|professional|commercial|military\s*grade|rugged)\b',
    re.IGNORECASE
)

# Standard accredited certification patterns
EXPLICIT_CERT_PATTERNS = [
    (r'\b(iso\s*9001|iso-9001|iso9001)\b', "ISO 9001 Certified"),
    (r'\b(iso\s*14001|iso-14001|iso14001)\b', "ISO 14001 Certified"),
    (r'\b(ul\s*listed|ul-listed|ul\s*certified)\b', "UL Listed"),
    (r'\b(ce\s*marked|ce\s*mark|ce\s*certified)\b', "CE Marked"),
    (r'\b(rohs|rohs\s*compliant)\b', "RoHS Compliant"),
    (r'\b(reach\s*compliant)\b', "REACH Compliant"),
    (r'\b(csa\s*certified|csa\s*approved)\b', "CSA Certified"),
    (r'\b(fcc\s*certified|fcc\s*approved)\b', "FCC Certified"),
    (r'\b(energy\s*star)\b', "Energy Star Certified"),
    (r'\b(atex\s*certified|atex\s*approved)\b', "ATEX Certified"),
]

# ── Keyword-based Category Mappings (Deterministic Fallback) ──────────────
KEYWORD_CATEGORY_MAP = [
    (r'\b(pump|pumps|impeller|fluid|centrifugal)\b', "Industrial Pumps"),
    (r'\b(generator|generators|turbine|alternator|genset)\b', "Generators"),
    (r'\b(solar|pv|photovoltaic|panel|module)\b', "Solar Equipment"),
    (r'\b(motor|engine|drive|servo)\b', "Motors & Drives"),
    (r'\b(valve|actuator|fitting|manifold)\b', "Valves & Fittings"),
    (r'\b(cable|wire|switch|circuit|breaker|relay)\b', "Electrical"),
    (r'\b(tool|drill|wrench|grinder)\b', "Tools"),
]

# ── Keyword-based Material Mappings (Deterministic Fallback) ──────────────
KEYWORD_MATERIAL_MAP = [
    (r'\b(stainless\s*steel|stainless|cast\s*iron|carbon\s*steel|alloy\s*steel)\b', "Stainless Steel"),
    (r'\b(aluminum|aluminium|anodized\s*aluminum)\b', "Aluminum"),
    (r'\b(plastic|pvc|polymer|polyethylene|polypropylene|abs)\b', "PVC / Polymer"),
    (r'\b(copper|brass|bronze)\b', "Copper / Brass"),
    (r'\b(silicon|monocrystalline|polycrystalline)\b', "Monocrystalline Silicon"),
    (r'\b(rubber|neoprene|nitrile|silicone\s*rubber)\b', "Rubber / Elastomer"),
]


def get_enrichment_mode() -> str:
    """Returns 'LLM' if GEMINI_API_KEY is set, else 'deterministic_fallback'."""
    return "LLM" if os.environ.get("GEMINI_API_KEY", "").strip() else "deterministic_fallback"

_get_enrichment_mode = get_enrichment_mode


# ── LEVEL 1: SOURCE-BASED DIRECT EXTRACTION ──────────────────────────────────

def _extract_from_source(
    product: dict[str, Any],
    missing_field_name: str,
    all_fields_for_product: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    """
    Level 1: Inspects existing uploaded fields, descriptions, or specs
    to find explicit, unambiguous values already in the source data.
    """
    target = missing_field_name.lower().strip()
    
    # Collect context blobs with field origins
    field_text_pairs = []
    for f in all_fields_for_product:
        f_val = str(f.get("value") or "").strip()
        f_name = f.get("field_name", "")
        if f_val:
            field_text_pairs.append((f_name, f_val))
        for ev in f.get("evidence", []):
            raw = str(ev.get("raw_value") or "").strip()
            if raw and raw != f_val:
                field_text_pairs.append((f"evidence:{f_name}", raw))

    if target == "certification":
        for src_name, text in field_text_pairs:
            for pattern, cert_val in EXPLICIT_CERT_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    return {
                        "field_name": "certification",
                        "value": cert_val,
                        "unit": None,
                        "confidence": 0.95,
                        "status": FieldStatus.VERIFIED,
                        "enrichment_method": EnrichmentMethod.SOURCE_DATA,
                        "is_verified": True,
                        "source_fields": src_name,
                        "reasoning": f"Explicit certification '{cert_val}' found in source field '{src_name}'.",
                        "source_label": "source_data",
                    }

    elif target == "voltage":
        for src_name, text in field_text_pairs:
            match = re.search(r'\b([0-9]{2,5})\s*(v|volts?|kv|vac|vdc)\b', text, re.IGNORECASE)
            if match:
                v_num = match.group(1)
                v_unit = "kV" if "kv" in match.group(2).lower() else "V"
                return {
                    "field_name": "voltage",
                    "value": v_num,
                    "unit": v_unit,
                    "confidence": 0.92,
                    "status": FieldStatus.VERIFIED,
                    "enrichment_method": EnrichmentMethod.SOURCE_DATA,
                    "is_verified": True,
                    "source_fields": src_name,
                    "reasoning": f"Explicit voltage measurement '{v_num}{v_unit}' extracted from '{src_name}'.",
                    "source_label": "source_data",
                }

    return None


# ── LEVEL 2: LLM-BASED ENRICHMENT (Gemini) ───────────────────────────────────

def _enrich_via_gemini(
    product_name: str,
    context_str: str,
    missing_field_name: str,
    api_key: str
) -> Optional[dict[str, Any]]:
    """
    Level 2: Call Gemini LLM with strict anti-hallucination and evidence guardrails.
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        prompt = (
            f"You are a strict product data intelligence engine. "
            f"Given the product context below, determine the '{missing_field_name}' attribute.\n\n"
            f"Product Name: {product_name}\n"
            f"Source Context: {context_str[:1500]}\n\n"
            f"CRITICAL RULES:\n"
            f"1. Never fabricate or invent certifications, dimensions, voltage, weight, or compliance data.\n"
            f"2. Words like 'industrial', 'heavy duty', 'premium', 'professional' are marketing terms, NOT certifications.\n"
            f"   If '{missing_field_name}' is 'certification' and no explicit accredited certification (e.g. ISO, CE, UL) is stated, "
            f"   return value: 'Unknown', status: 'needs_review', confidence: 0.0, reasoning: 'No reliable certification evidence was provided.'\n"
            f"3. For other fields, if there is insufficient evidence to determine '{missing_field_name}' without guessing, "
            f"   return value: 'Unknown', status: 'needs_review', confidence: 0.0, reasoning: 'Insufficient source evidence.'\n"
            f"4. If directly supported by the context, set status: 'extracted' and confidence: 0.85-0.95.\n"
            f"5. If reasonably inferred from product classification, set status: 'inferred' and confidence: 0.55-0.69.\n\n"
            f"Respond ONLY in valid JSON with these exact keys:\n"
            f'{{"value": "...", "unit": null, "confidence": 0.65, "status": "inferred", "reasoning": "...", "source_fields": "name, description"}}'
        )

        response = model.generate_content(prompt)
        text = response.text.strip()

        json_match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
        if not json_match:
            return None

        import json
        parsed = json.loads(json_match.group())
        val = parsed.get("value")
        if not val or val.lower() in ("null", "none"):
            val = "Unknown"

        status_str = parsed.get("status", "inferred").lower()
        conf = float(parsed.get("confidence", 0.60))

        if val == "Unknown" or conf < 0.50 or status_str == "needs_review":
            field_status = FieldStatus.NEEDS_REVIEW
            method = EnrichmentMethod.NO_EVIDENCE
            is_ver = False
        elif status_str in ("extracted", "verified") and conf >= 0.85:
            field_status = FieldStatus.VERIFIED
            method = EnrichmentMethod.LLM
            is_ver = True
        else:
            field_status = FieldStatus.INFERRED
            method = EnrichmentMethod.LLM
            is_ver = False

        return {
            "field_name": missing_field_name,
            "value": str(val),
            "unit": parsed.get("unit"),
            "confidence": min(0.95, max(0.0, conf)),
            "status": field_status,
            "enrichment_method": method,
            "is_verified": is_ver,
            "source_fields": parsed.get("source_fields", "context"),
            "reasoning": parsed.get("reasoning", "Inferred by Gemini LLM based on source context."),
            "source_label": "llm",
        }
    except Exception as e:
        print(f"[Catalog Enrichment] Gemini call failed for '{missing_field_name}': {e}")
        return None


# ── LEVEL 3: DETERMINISTIC RULE-BASED FALLBACK ──────────────────────────────

def _enrich_deterministic(
    context_lower: str,
    missing_field_name: str,
    product_name: str,
    all_fields_for_product: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Level 3: Deterministic rule-based fallback when LLM is unavailable.
    - Category & Material: Rule-inferred with confidence ~0.62–0.65 (status: INFERRED).
    - Certification: NEVER infer from marketing keywords; returns 'Unknown' (status: NEEDS_REVIEW, confidence: 0.0).
    """
    target = missing_field_name.lower().strip()

    if target == "category":
        for pattern, cat in KEYWORD_CATEGORY_MAP:
            match = re.search(pattern, context_lower)
            if match:
                kw = match.group(0)
                return {
                    "field_name": "category",
                    "value": cat,
                    "unit": None,
                    "confidence": 0.62,
                    "status": FieldStatus.INFERRED,
                    "enrichment_method": EnrichmentMethod.DETERMINISTIC_FALLBACK,
                    "is_verified": False,
                    "source_fields": "name",
                    "reasoning": f"Inferred from product terminology (keyword: '{kw}').",
                    "source_label": "deterministic_fallback",
                }
        return {
            "field_name": "category",
            "value": "Unknown",
            "unit": None,
            "confidence": 0.0,
            "status": FieldStatus.NEEDS_REVIEW,
            "enrichment_method": EnrichmentMethod.NO_EVIDENCE,
            "is_verified": False,
            "source_fields": "name",
            "reasoning": "No recognizable category terminology found in product name or context.",
            "source_label": "deterministic_fallback",
        }

    elif target == "material":
        for pattern, mat in KEYWORD_MATERIAL_MAP:
            match = re.search(pattern, context_lower)
            if match:
                kw = match.group(0)
                return {
                    "field_name": "material",
                    "value": mat,
                    "unit": None,
                    "confidence": 0.65,
                    "status": FieldStatus.INFERRED,
                    "enrichment_method": EnrichmentMethod.DETERMINISTIC_FALLBACK,
                    "is_verified": False,
                    "source_fields": "name, specifications",
                    "reasoning": f"Inferred from product specifications (keyword: '{kw}').",
                    "source_label": "deterministic_fallback",
                }
        return {
            "field_name": "material",
            "value": "Unknown",
            "unit": None,
            "confidence": 0.0,
            "status": FieldStatus.NEEDS_REVIEW,
            "enrichment_method": EnrichmentMethod.NO_EVIDENCE,
            "is_verified": False,
            "source_fields": "specifications",
            "reasoning": "No material keywords detected in product specifications.",
            "source_label": "deterministic_fallback",
        }

    elif target == "certification":
        # Check for explicit accredited certification patterns first
        for pattern, cert in EXPLICIT_CERT_PATTERNS:
            if re.search(pattern, context_lower):
                return {
                    "field_name": "certification",
                    "value": cert,
                    "unit": None,
                    "confidence": 0.85,
                    "status": FieldStatus.ENRICHED,
                    "enrichment_method": EnrichmentMethod.DETERMINISTIC_FALLBACK,
                    "is_verified": True,
                    "source_fields": "specifications",
                    "reasoning": f"Matched explicit standard certification '{cert}' in text.",
                    "source_label": "deterministic_fallback",
                }

        # IMPORTANT: Marketing buzzwords like "industrial", "heavy duty", "premium"
        # must NEVER fabricate a certification like "Industrial Duty Rated"
        return {
            "field_name": "certification",
            "value": "Unknown",
            "unit": None,
            "confidence": 0.0,
            "status": FieldStatus.NEEDS_REVIEW,
            "enrichment_method": EnrichmentMethod.NO_EVIDENCE,
            "is_verified": False,
            "source_fields": "name",
            "reasoning": "No reliable certification evidence was provided in product data.",
            "source_label": "deterministic_fallback",
        }

    elif target == "voltage":
        match = re.search(r'\b([0-9]{2,5})\s*(v|volts?|kv)\b', context_lower)
        if match:
            v_val = match.group(1)
            v_unit = "kV" if "kv" in match.group(2).lower() else "V"
            return {
                "field_name": "voltage",
                "value": v_val,
                "unit": v_unit,
                "confidence": 0.70,
                "status": FieldStatus.INFERRED,
                "enrichment_method": EnrichmentMethod.DETERMINISTIC_FALLBACK,
                "is_verified": False,
                "source_fields": "description",
                "reasoning": f"Extracted voltage {v_val}{v_unit} from text context via pattern match.",
                "source_label": "deterministic_fallback",
            }
        return {
            "field_name": "voltage",
            "value": "Unknown",
            "unit": None,
            "confidence": 0.0,
            "status": FieldStatus.NEEDS_REVIEW,
            "enrichment_method": EnrichmentMethod.NO_EVIDENCE,
            "is_verified": False,
            "source_fields": "description",
            "reasoning": "No electrical voltage specifications found in product data.",
            "source_label": "deterministic_fallback",
        }

    return {
        "field_name": missing_field_name,
        "value": "Unknown",
        "unit": None,
        "confidence": 0.0,
        "status": FieldStatus.NEEDS_REVIEW,
        "enrichment_method": EnrichmentMethod.NO_EVIDENCE,
        "is_verified": False,
        "source_fields": "context",
        "reasoning": f"No reliable evidence available for field '{missing_field_name}'.",
        "source_label": "deterministic_fallback",
    }


# ── MAIN ORCHESTRATOR ────────────────────────────────────────────────────────

def enrich_missing_field(
    product: dict[str, Any],
    missing_field_name: str,
    all_fields_for_product: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    3-Tier Enrichment Pipeline for a single missing field:
    1. Check source data for direct evidence.
    2. Try LLM (Gemini) if API key is present.
    3. Fall back to honest deterministic rule engine.
    """
    # ── Level 1: Source / Evidence Extraction ──
    level1_res = _extract_from_source(product, missing_field_name, all_fields_for_product)
    if level1_res:
        return level1_res

    # Build context string
    p_name = product.get("name", "")
    all_text_blobs = [p_name]
    for f in all_fields_for_product:
        if f.get("value"):
            all_text_blobs.append(f"{f.get('field_name')}: {f.get('value')}")
            for ev in f.get("evidence", []):
                if ev.get("raw_value"):
                    all_text_blobs.append(ev.get("raw_value"))

    context_str = " ".join(all_text_blobs)
    context_lower = context_str.lower()

    # ── Level 2: LLM Enrichment (Gemini) ──
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if api_key:
        level2_res = _enrich_via_gemini(p_name, context_str, missing_field_name, api_key)
        if level2_res:
            return level2_res

    # ── Level 3: Deterministic Rule Fallback ──
    return _enrich_deterministic(context_lower, missing_field_name, p_name, all_fields_for_product)


def enrich_product_missing_fields(product_id: str) -> dict[str, Any]:
    """
    Identifies missing fields for a product, runs 3-tier enrichment,
    and writes ProductField + FieldEvidence records with full audit trail.
    """
    product = catalog_db.get_product_with_details(product_id)
    if not product:
        raise ValueError(f"Product '{product_id}' not found.")

    existing_fields = product.get("fields", [])
    # Fields that currently have non-empty, non-Unknown values
    existing_valid_names = {
        f["field_name"].lower()
        for f in existing_fields
        if f.get("value") and f.get("value") != "Unknown"
    }

    missing_targets = [f for f in EXPECTED_DEFAULT_FIELDS if f not in existing_valid_names]

    enriched_results = []
    enrichment_mode = get_enrichment_mode()

    for target in missing_targets:
        enrichment = enrich_missing_field(product, target, existing_fields)
        if enrichment:
            # Check if an existing field record with 'missing' or 'unknown' exists to update
            existing_f_rec = next(
                (f for f in existing_fields if f["field_name"].lower() == target), None
            )
            field_id = existing_f_rec["id"] if existing_f_rec else None

            pf_obj = ProductField(
                id=field_id or str(uuid_gen()),
                product_id=product_id,
                field_name=enrichment["field_name"],
                value=enrichment["value"],
                unit=enrichment.get("unit"),
                status=enrichment["status"],
                confidence=enrichment["confidence"],
                enrichment_method=enrichment["enrichment_method"],
                is_verified=enrichment.get("is_verified", False),
                source_fields=enrichment.get("source_fields"),
                reasoning=enrichment.get("reasoning"),
            )
            catalog_db.save_product_field(pf_obj)

            # Create FieldEvidence record
            fe_obj = FieldEvidence(
                product_field_id=pf_obj.id,
                source_label=enrichment["source_label"],
                raw_value=enrichment["reasoning"]
            )
            catalog_db.save_field_evidence(fe_obj)

            enriched_results.append({
                "field_name": enrichment["field_name"],
                "value": enrichment["value"],
                "unit": enrichment.get("unit"),
                "confidence": enrichment["confidence"],
                "status": enrichment["status"].value,
                "enrichment_method": enrichment["enrichment_method"].value,
                "is_verified": enrichment.get("is_verified", False),
                "source_fields": enrichment.get("source_fields"),
                "reasoning": enrichment["reasoning"],
                "source_label": enrichment["source_label"],
            })

    return {
        "enriched_count": len(enriched_results),
        "enrichment_mode": enrichment_mode,
        "enriched_fields": enriched_results,
    }


def uuid_gen() -> str:
    import uuid
    return str(uuid.uuid4())
