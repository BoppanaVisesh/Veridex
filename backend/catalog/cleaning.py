"""
Catalog Intelligence — Field Cleaning & Normalization Module (§Catalog)

Normalizes raw field names, strips HTML noise, parses & standardizes units,
and flags ambiguous or conflicting field values.
"""

from __future__ import annotations

import re
from typing import Optional, Any
from bs4 import BeautifulSoup

from backend.catalog.catalog_models import FieldStatus


SYNONYM_MAP: dict[str, str] = {
    # Weight synonyms
    "wt": "weight",
    "weight": "weight",
    "weight (kg)": "weight",
    "weight (lbs)": "weight",
    "weight (g)": "weight",
    "gross weight": "weight",
    "net weight": "weight",
    "product weight": "weight",

    # Dimensions synonyms
    "dimensions": "dimensions",
    "dim": "dimensions",
    "dims": "dimensions",
    "size": "dimensions",
    "dimensions (l x w x h)": "dimensions",
    "dimensions (mm)": "dimensions",
    "overall dimensions": "dimensions",

    # Material synonyms
    "material": "material",
    "mat": "material",
    "material type": "material",
    "construction": "material",
    "casing material": "material",

    # Voltage synonyms
    "voltage": "voltage",
    "volt": "voltage",
    "volts": "voltage",
    "input voltage": "voltage",
    "operating voltage": "voltage",
    "v": "voltage",
    "voltage rating": "voltage",

    # Category synonyms
    "category": "category",
    "product category": "category",
    "cat": "category",
    "type": "category",
    "product type": "category",

    # Color synonyms
    "color": "color",
    "colour": "color",
    "finish": "color",
    "surface finish": "color",

    # Certification synonyms
    "certification": "certification",
    "certifications": "certification",
    "cert": "certification",
    "compliance": "certification",
    "safety rating": "certification",

    # Power synonyms
    "power": "power",
    "wattage": "power",
    "power rating": "power",
    "watts": "power",
}


UNIT_PATTERNS: list[dict[str, Any]] = [
    {
        "type": "weight",
        "regex": r'^\s*([0-9]+(?:\.[0-9]+)?)\s*(kg|kilograms?|g|grams?|lbs?|pounds?|oz|ounces?)\s*$',
        "unit_map": {"kg": "kg", "kilogram": "kg", "kilograms": "kg", "g": "g", "gram": "g", "grams": "g",
                     "lb": "lbs", "lbs": "lbs", "pound": "lbs", "pounds": "lbs", "oz": "oz", "ounce": "oz", "ounces": "oz"}
    },
    {
        "type": "voltage",
        "regex": r'^\s*([0-9]+(?:\.[0-9]+)?)\s*(v|volts?|kv|kilovolts?)\s*$',
        "unit_map": {"v": "V", "volt": "V", "volts": "V", "kv": "kV", "kilovolt": "kV", "kilovolts": "kV"}
    },
    {
        "type": "power",
        "regex": r'^\s*([0-9]+(?:\.[0-9]+)?)\s*(w|watts?|kw|kilowatts?|hp)\s*$',
        "unit_map": {"w": "W", "watt": "W", "watts": "W", "kw": "kW", "kilowatt": "kW", "kilowatts": "kW", "hp": "hp"}
    },
    {
        "type": "dimension",
        "regex": r'^\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|m|meters?|inches?|in|ft|feet)\s*$',
        "unit_map": {"mm": "mm", "cm": "cm", "m": "m", "meter": "m", "meters": "m",
                     "in": "in", "inch": "in", "inches": "in", "ft": "ft", "feet": "ft"}
    }
]


def strip_html_noise(value: str) -> str:
    """Remove HTML tags, excessive whitespace, and boilerplate phrases."""
    if not value:
        return ""
    # Strip HTML tags
    cleaned = BeautifulSoup(value, "html.parser").get_text() if '<' in value else value
    # Collapse whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def normalize_field_name(name: str) -> str:
    """Lowercase, strip whitespace, and collapse synonyms to standard field names."""
    if not name:
        return "unknown_field"
    
    clean_name = name.lower().strip()
    clean_name = re.sub(r'[^\w\s\(\)\-\/]', '', clean_name)
    
    return SYNONYM_MAP.get(clean_name, clean_name.replace(' ', '_'))


def normalize_units(field_name: str, value: str) -> tuple[str, Optional[str], FieldStatus]:
    """
    Detect and standardize units for field values.
    Returns (standardized_value, unit, status).
    If ambiguous or multi-value range, leaves value as-is and flags status as 'flagged'.
    """
    if not value:
        return ("", None, FieldStatus.MISSING)

    val_clean = value.strip()

    # Check for ambiguity signals (e.g. ranges "10-20 kg", multiple numbers, "varies")
    if re.search(r'\b(varies|unknown|n/a|tbd|approx|or)\b', val_clean, re.IGNORECASE):
        return (val_clean, None, FieldStatus.FLAGGED)

    # Multi-value or ambiguous range pattern (e.g. "10 - 20 kg" or "100 / 200 V")
    if re.search(r'[0-9]+\s*[\-\/]\s*[0-9]+', val_clean):
        return (val_clean, None, FieldStatus.FLAGGED)

    # Try unit regex matches
    for rule in UNIT_PATTERNS:
        match = re.match(rule["regex"], val_clean, re.IGNORECASE)
        if match:
            num_part = match.group(1)
            raw_unit = match.group(2).lower()
            std_unit = rule["unit_map"].get(raw_unit, raw_unit)
            return (num_part, std_unit, FieldStatus.RAW)

    # If no numeric unit pattern matched, return clean value without unit
    return (val_clean, None, FieldStatus.RAW)


def clean_and_normalize(raw_product: dict[str, Any]) -> dict[str, Any]:
    """
    Takes ingestion output product dict, normalizes fields and units,
    deduplicates fields (combining evidence), and returns cleaned structure.
    """
    p_name = raw_product.get("product_name", "Unnamed Product")
    raw_source = raw_product.get("raw_source_type")
    raw_fields = raw_product.get("fields", [])

    field_map: dict[str, dict[str, Any]] = {}

    for rf in raw_fields:
        f_name_raw = rf.get("field_name", "")
        r_val = rf.get("raw_value", "")
        src_lbl = rf.get("source_label", "upload")

        clean_val = strip_html_noise(r_val)
        if not clean_val:
            continue

        norm_name = normalize_field_name(f_name_raw)
        val, unit, status = normalize_units(norm_name, clean_val)

        evidence_entry = {
            "source_label": src_lbl,
            "raw_value": r_val
        }

        if norm_name in field_map:
            # Existing field: append evidence
            field_map[norm_name]["evidence"].append(evidence_entry)
            # If current value was flagged or empty, update if new value is cleaner
            if field_map[norm_name]["status"] == FieldStatus.FLAGGED and status != FieldStatus.FLAGGED:
                field_map[norm_name]["value"] = val
                field_map[norm_name]["unit"] = unit
                field_map[norm_name]["status"] = status
        else:
            field_map[norm_name] = {
                "field_name": norm_name,
                "value": val,
                "unit": unit,
                "status": status,
                "confidence": 0.8 if status != FieldStatus.FLAGGED else 0.4,
                "evidence": [evidence_entry]
            }

    return {
        "product_name": p_name,
        "raw_source_type": raw_source,
        "fields": list(field_map.values())
    }
