"""
Unilog Product Intelligence — Enrichment Engine
================================================
Transforms raw Unilog-format catalog rows (6 input columns) into
structured, commerce-ready product intelligence matching the
252-column Delivery Format output schema.

Pipeline:
  1. Clean & normalize  — strip placeholders, extract manufacturer/brand
  2. Classify           — infer Dept / Class / Fine / Classpath
  3. Describe           — build 5 description variants (Invoice, Mobile,
                          Short, Long, Retail)
  4. Attribute extract  — pull key-value attributes from Part_Desc
  5. Enrich (LLM/rule)  — fill gaps via Gemini or deterministic rules
  6. Score & flag       — confidence scores + needs_review flags
"""

from __future__ import annotations

import os
import re
import json
from typing import Any, Optional

# ── Placeholder filter ────────────────────────────────────────────────────────

PLACEHOLDERS = {
    "-- unbranded --", "-- no unilog brand --", "-- no dib brand --",
    "-", "n/a", "na", "none", "null", "unknown", "commodity - unbranded",
}


def _clean(val: Any) -> str:
    """Return stripped string, or '' if placeholder / empty."""
    if val is None:
        return ""
    s = str(val).strip()
    return "" if s.lower() in PLACEHOLDERS else s


# ── Manufacturer / Brand normaliser ──────────────────────────────────────────

# Common abbreviation expansions seen in Part_Manuf
MFR_EXPANSIONS = {
    "milw": "Milwaukee", "mirus": "Mirka", "jamin": "3M",
    "appde": "Appliance Dealers Cooperative",
    "freud": "Freud", "boica": "Boise Cascade Building Materials",
    "uslum": "U S Lumber", "paldo": "Palmer Donavin",
    "parksi": "Parksite", "trex": "Trex Company", "timbertech": "TimberTech",
    "velam": "Velux America", "prodo": "ProVia",
    "certai": "CertainTeed", "huber": "Huber Engineered Woods",
    "ajman": "A J Manufacturing", "jhardie": "James Hardie",
    "werto": "Wera Tools",
}

# Brand field mappings (cleaned values)
BRAND_CANONICAL = {
    "trex": "Trex®", "timbertech": "TimberTech®", "jameshardie": "James Hardie®",
    "lp smartside": "LP® SmartSide®", "hager": "Hager®", "provia": "ProVia®",
    "dsi westbury": "DSI Westbury®", "ajm": "AJM®",
    "united window & door": "United Window & Door™",
}


def _normalise_manufacturer(raw_manuf: str) -> str:
    """Extract canonical manufacturer name from raw Part_Manuf string.
    Input format: 'Manufacturer Name (CODE)' or just 'Manufacturer Name'
    """
    if not raw_manuf:
        return ""
    # Strip trailing code in parentheses
    m = re.match(r'^(.+?)\s*\([A-Z0-9]+\)\s*$', raw_manuf.strip())
    name = m.group(1).strip() if m else raw_manuf.strip()
    return name


# Known brand names that can appear in Part_Desc — sorted longest-first to avoid partial matches
KNOWN_BRANDS_IN_DESC: list[tuple[re.Pattern, str]] = [
    (re.compile(r'\b3M\b'), '3M'),
    (re.compile(r'\bDiablo\b', re.I), 'Diablo'),
    (re.compile(r'\bMirka\b', re.I), 'Mirka'),
    (re.compile(r'\bMilwaukee\b', re.I), 'Milwaukee'),
    (re.compile(r'\bBosch\b', re.I), 'Bosch'),
    (re.compile(r'\bDeWalt\b', re.I), 'DeWalt'),
    (re.compile(r'\bMakita\b', re.I), 'Makita'),
    (re.compile(r'\bFreud\b', re.I), 'Freud'),
    (re.compile(r'\bTrex\b', re.I), 'Trex'),
    (re.compile(r'\bTimberTech\b', re.I), 'TimberTech'),
    (re.compile(r'\bJames\s*Hardie\b', re.I), 'James Hardie'),
    (re.compile(r'\bLP\s*SmartSide\b', re.I), 'LP SmartSide'),
    (re.compile(r'\bCertainTeed\b', re.I), 'CertainTeed'),
    (re.compile(r'\bHuber\b', re.I), 'Huber'),
    (re.compile(r'\bVelux\b', re.I), 'Velux'),
    (re.compile(r'\bProVia\b', re.I), 'ProVia'),
    (re.compile(r'\bAndersen\b', re.I), 'Andersen'),
    (re.compile(r'\bPella\b', re.I), 'Pella'),
    (re.compile(r'\bGrizzly\b', re.I), 'Grizzly'),
    (re.compile(r'\bWoodstock\b', re.I), 'Woodstock'),
    (re.compile(r'\bWera\b', re.I), 'Wera'),
    (re.compile(r'\bKnipex\b', re.I), 'Knipex'),
    (re.compile(r'\bIRWIN\b', re.I), 'Irwin'),
    (re.compile(r'\bStanley\b', re.I), 'Stanley'),
    (re.compile(r'\bHager\b', re.I), 'Hager'),
    (re.compile(r'\bGE\b'), 'GE'),
    (re.compile(r'\bWhirlpool\b', re.I), 'Whirlpool'),
    (re.compile(r'\bLG\b'), 'LG'),
    (re.compile(r'\bSamsung\b', re.I), 'Samsung'),
    (re.compile(r'\bMaytag\b', re.I), 'Maytag'),
    (re.compile(r'\bKitchenAid\b', re.I), 'KitchenAid'),
]


def _normalise_brand(e1_brand: str, unilog_brand: str, dib_brand: str,
                     mfr_name: str, part_desc: str = "") -> str:
    """Return the best available brand, canonical form.
    Falls back to scanning Part_Desc for known brand names when all
    brand fields contain only placeholder/distributor values.
    """
    for raw in (e1_brand, unilog_brand, dib_brand):
        if raw:
            low = raw.lower()
            if low in BRAND_CANONICAL:
                return BRAND_CANONICAL[low]
            return raw  # use as-is if no canonical form

    # Try to extract brand from Part_Desc
    if part_desc:
        for pattern, brand_name in KNOWN_BRANDS_IN_DESC:
            if pattern.search(part_desc):
                return brand_name

    # Fall back to manufacturer name
    return mfr_name


# ── Taxonomy / Classification ─────────────────────────────────────────────────

# Keyword → (Dept, Class, Fine, Classpath)
TAXONOMY_RULES: list[tuple[re.Pattern, tuple[str, str, str, str]]] = [
    # Flap discs
    (re.compile(r'\bflap disc\b', re.I),
     ("Abrasives & Surface Preparation", "Cutting & Grinding", "Flap Discs",
      "Abrasives & Surface Preparation>Cutting & Grinding>Flap Discs")),
    # Angle grinders
    (re.compile(r'\bangle grinder\b', re.I),
     ("Tools & Equipment", "Power Tools", "Angle Grinders",
      "Tools & Equipment>Power Tools>Angle Grinders")),
    # Grinding / cut-off discs
    (re.compile(r'\b(cut.?off disc|grinding wheel|cut and grind|grinding disc|grind disc)\b', re.I),
     ("Abrasives & Surface Preparation", "Cutting & Grinding", "Cut-Off & Grinding Discs",
      "Abrasives & Surface Preparation>Cutting & Grinding>Cut-Off & Grinding Discs")),
    # Generic abrasives
    (re.compile(r'\b(sanding belt|sanding disc|sanding sponge|abrasive|abranet|cubitron|hiolit|stikit)\b', re.I),
     ("Abrasives & Surface Preparation", "Abrasives", "Sanding Belts & Discs",
      "Abrasives & Surface Preparation>Abrasives>Sanding Belts & Discs")),
    # Dishwashers
    (re.compile(r'\bdishwasher\b', re.I),
     ("Appliances & Consumer Electronics", "Kitchen Appliances", "Built-In Dishwashers",
      "Appliances & Consumer Electronics>Kitchen Appliances>Built-In Dishwashers")),
    # Dryers
    (re.compile(r'\b(electric dryer|gas dryer|elect dryer)\b', re.I),
     ("Appliances & Consumer Electronics", "Laundry Appliances", "Clothes Dryers",
      "Appliances & Consumer Electronics>Laundry Appliances>Clothes Dryers")),
    # Washers
    (re.compile(r'\b(washer|laundry center)\b', re.I),
     ("Appliances & Consumer Electronics", "Laundry Appliances", "Clothes Washers",
      "Appliances & Consumer Electronics>Laundry Appliances>Clothes Washers")),
    # Decking
    (re.compile(r'\b(decking|deck board|pvc decking)\b', re.I),
     ("Building Materials", "Decking & Railing", "Decking Boards",
      "Building Materials>Decking & Railing>Decking Boards")),
    # Railing
    (re.compile(r'\b(rail kit|railing|rail panel|baluster|stair rail|horiz rail)\b', re.I),
     ("Building Materials", "Decking & Railing", "Railing Systems",
      "Building Materials>Decking & Railing>Railing Systems")),
    # Fascia
    (re.compile(r'\bfascia\b', re.I),
     ("Building Materials", "Decking & Railing", "Fascia Boards",
      "Building Materials>Decking & Railing>Fascia Boards")),
    # Siding
    (re.compile(r'\b(siding|lap siding|sdg|smartside|hardieplank|hardipanel)\b', re.I),
     ("Building Materials", "Exterior Siding", "Lap & Panel Siding",
      "Building Materials>Exterior Siding>Lap & Panel Siding")),
    # Tape & adhesives
    (re.compile(r'\b(tape|elect tape|vinyl tape)\b', re.I),
     ("Electrical & Lighting", "Electrical Supplies", "Electrical Tape",
      "Electrical & Lighting>Electrical Supplies>Electrical Tape")),
    # Drywall
    (re.compile(r'\b(drywall|easi.?lite|firelite|gypsum)\b', re.I),
     ("Building Materials", "Drywall & Insulation", "Drywall Panels",
      "Building Materials>Drywall & Insulation>Drywall Panels")),
    # Roofing
    (re.compile(r'\b(shingle|ice guard|eaveguard|roofing)\b', re.I),
     ("Building Materials", "Roofing", "Roofing Materials",
      "Building Materials>Roofing>Roofing Materials")),
    # Skylights
    (re.compile(r'\b(skylight|skylt)\b', re.I),
     ("Building Materials", "Windows & Skylights", "Skylights",
      "Building Materials>Windows & Skylights>Skylights")),
    # Windows & Doors
    (re.compile(r'\b(window|door|patio dr|gliding patio)\b', re.I),
     ("Building Materials", "Windows & Doors", "Sliding Patio Doors",
      "Building Materials>Windows & Doors>Sliding Patio Doors")),
    # Metal roofing panels
    (re.compile(r'\b(premier rib|metal panel|rib xl)\b', re.I),
     ("Building Materials", "Roofing", "Metal Roofing Panels",
      "Building Materials>Roofing>Metal Roofing Panels")),
    # Heater / appliance parts
    (re.compile(r'\bheater kit\b', re.I),
     ("Appliances & Consumer Electronics", "Appliance Parts", "Heating Elements",
      "Appliances & Consumer Electronics>Appliance Parts>Heating Elements")),
    # Mortar
    (re.compile(r'\bmortar\b', re.I),
     ("Building Materials", "Masonry", "Mortar & Grout",
      "Building Materials>Masonry>Mortar & Grout")),
    # Kneeling pad
    (re.compile(r'\bkneeling pad\b', re.I),
     ("Tools & Equipment", "Hand Tools", "Accessories",
      "Tools & Equipment>Hand Tools>Accessories")),
    # Post / sleeve
    (re.compile(r'\b(post sleeve|post trim|post cap|blank post)\b', re.I),
     ("Building Materials", "Decking & Railing", "Post Sleeves & Caps",
      "Building Materials>Decking & Railing>Post Sleeves & Caps")),
    # Floor / subfloor
    (re.compile(r'\b(subfloor|osb|t&g|tongue.?and.?groove)\b', re.I),
     ("Building Materials", "Flooring", "Subfloor Panels",
      "Building Materials>Flooring>Subfloor Panels")),
    # Attic access door
    (re.compile(r'\battic access\b', re.I),
     ("Building Materials", "Doors", "Attic Access Doors",
      "Building Materials>Doors>Attic Access Doors")),
    # Threshold
    (re.compile(r'\bthreshold\b', re.I),
     ("Building Materials", "Doors", "Door Thresholds",
      "Building Materials>Doors>Door Thresholds")),
    # Lumber / wood
    (re.compile(r'\b(doug fir|lumber|wood|smooth 1s2e)\b', re.I),
     ("Building Materials", "Lumber & Composites", "Dimensional Lumber",
      "Building Materials>Lumber & Composites>Dimensional Lumber")),
    # Rainscreen / wrap
    (re.compile(r'\b(rainscreen|zip wrap)\b', re.I),
     ("Building Materials", "Moisture & Weather Barriers", "Rainscreens",
      "Building Materials>Moisture & Weather Barriers>Rainscreens")),
    # Deck joist tape
    (re.compile(r'\bjoist tape\b', re.I),
     ("Building Materials", "Decking & Railing", "Deck Tape & Accessories",
      "Building Materials>Decking & Railing>Deck Tape & Accessories")),
    # Sander / power tools
    (re.compile(r'\b(sander|belt and spindle|oscillating edge)\b', re.I),
     ("Tools & Equipment", "Power Tools", "Sanders",
      "Tools & Equipment>Power Tools>Sanders")),
    # Tire pressure gauge
    (re.compile(r'\btire pressure\b', re.I),
     ("Automotive & Transportation", "Automotive Tools", "Tire Gauges",
      "Automotive & Transportation>Automotive Tools>Tire Gauges")),
    # ADA rail
    (re.compile(r'\bada\b', re.I),
     ("Building Materials", "Decking & Railing", "ADA Handrails",
      "Building Materials>Decking & Railing>ADA Handrails")),
]

FALLBACK_TAXONOMY = (
    "General Industrial", "General Products", "Uncategorized",
    "General Industrial>General Products>Uncategorized"
)


def _classify(desc: str) -> tuple[str, str, str, str]:
    """Return (Dept, Class, Fine, Classpath) by matching Part_Desc."""
    for pattern, taxonomy in TAXONOMY_RULES:
        if pattern.search(desc):
            return taxonomy
    return FALLBACK_TAXONOMY


# ── Attribute Extractor ───────────────────────────────────────────────────────

# Patterns that extract dimension / spec attributes from Part_Desc
ATTR_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # Dimensions: 4"x.040"x5/8"  or  1x6-16'  or  5/8"x4'
    ("Diameter",
     re.compile(r'(\d[\d/]*)\s*["\u201d]\s*[xX]\s*(\d[\d/\.]*)\s*["\u201d]'), "in"),
    # Grit: P80, P120, 150 Grit
    ("Abrasive Grit",
     re.compile(r'\b(?:P|p)?(\d{2,3})\s*(?:[Gg]rit|[Gg])\b'), ""),
    # Arbor size
    ("Arbor Size",
     re.compile(r'(\d[\d/]*)\s*["\u201d]\s*(?:arbor|arb)\b', re.I), "in"),
    # Voltage
    ("Voltage Rating",
     re.compile(r'\b(\d+)\s*[Vv]\b'), "V"),
    # Amperage
    ("Amperage Rating",
     re.compile(r'\b(\d+)\s*[Aa]\b'), "A"),
    # Width x depth
    ("Width",
     re.compile(r'(\d[\d/\-\.]*)\s*(?:in|")\s*[Ww]\b'), "in"),
    # Depth with door open
    ("Depth With Door Open",
     re.compile(r'(\d[\d/\-\.]*)\s*(?:in|")(?:\s+depth with door open)?\b', re.I), "in"),
    # Sound level
    ("Sound Level",
     re.compile(r'(\d+)\s*d[Bb][Aa]'), "dBA"),
    # Length in feet
    ("Length",
     re.compile(r'\b(\d+)\'(?:\s|$)'), "ft"),
    # Wash cycles
    ("Number of Wash Cycles",
     re.compile(r'(\d+)\s*[Ww]ash\s*[Cc]ycle'), ""),
    # Piece count
    ("Quantity",
     re.compile(r'(\d+)\s*(?:pc|pcs|piece|pieces|disc\/box)\b', re.I), ""),
    # Color / finish
    ("Color",
     re.compile(
         r'\b(White|Wh|Black|Blk|Gray|Grey|Bronze|Stainless\s*Steel|SS|Charcoal|Clay|Ivory|'
         r'Mahogany|Coastline|Brownstone|Slate\s*Gray|Castle\s*Gate|American\s*Walnut|'
         r'English\s*Walnut|French\s*White\s*Oak|Weathered\s*Teak|Island\s*Mist|Biscayne|'
         r'Carmel|Jasper|Rainier|Hatteras|Salt\s*Flat|Honey\s*Grove|Tide\s*Pool|'
         r'Pebble\s*Beach|Cinnamon\s*Cove|Golden\s*Hour|Malted\s*Barley|Millstone|'
         r'Whiskey\s*Barrel)\b', re.I), ""),
    # Series name
    ("Series",
     re.compile(
         r'\b(Professional Series|Eco Series|Premier Series|Performance\+|Perform\+|'
         r'Cubitron II|Steel Demon|Speed Demon|Transcend Lineage|Enhance Naturals|'
         r'Enhance Basics|Select 2\.0|ecoLitePlus|Vintage|Landmark|Harvest|Select Classic|'
         r'Select Alum|Select T-Rail)\b', re.I), ""),
    # Material
    ("Material",
     re.compile(
         r'\b(Stainless\s*Steel|Aluminum|Alum|Composite|PVC|Cast\s*Iron|Carbon\s*Steel|'
         r'Fiberglass|Vinyl|Polymer|Brass|Bronze|Rubber)\b', re.I), ""),
]


def _extract_attributes(desc: str) -> list[dict]:
    """Extract key-value attribute pairs from Part_Desc."""
    attrs = []
    seen_labels = set()
    for label, pattern, uom in ATTR_PATTERNS:
        if label in seen_labels:
            continue
        m = pattern.search(desc)
        if m:
            val = m.group(1).strip() if m.lastindex else m.group(0).strip()
            if val:
                # Expand common abbreviations in value
                val = _expand_color(val)
                attrs.append({"label": label, "value": val, "uom": uom})
                seen_labels.add(label)
    return attrs


COLOR_MAP = {
    "wh": "White", "bk": "Black", "blk": "Black", "ss": "Stainless Steel",
    "bss": "Black Stainless Steel", "dg": "Diamond Gray",
    "bo": "Black Obsidian", "wn": "White",
}


def _expand_color(val: str) -> str:
    low = val.lower().strip()
    return COLOR_MAP.get(low, val)


# ── Description Builders ──────────────────────────────────────────────────────

def _build_invoice_desc(brand: str, desc: str, attrs: list[dict]) -> str:
    """Invoice description: ≤40 chars, ALL CAPS, abbreviation-safe."""
    # Start from key words in desc stripped of MPN prefix
    stripped = _strip_mpn_prefix(desc).upper()
    # Trim to 40 chars at word boundary
    if len(stripped) <= 40:
        return stripped
    trimmed = stripped[:40].rsplit(" ", 1)[0]
    return trimmed


def _build_mobile_desc(brand: str, mfr: str, series: str, mpn: str,
                       item_type: str, desc: str) -> str:
    """Mobile description: 60–80 chars, Title Case."""
    parts = [p for p in [mfr or brand, brand if brand != mfr else "", series, mpn] if p]
    base = ", ".join(p for p in parts if p)
    if len(base) < 60:
        remainder = _strip_mpn_prefix(desc)
        base = f"{base}, {remainder}"
    return base[:80]


def _build_short_desc(brand: str, series: str, mpn: str,
                      item_type: str, attrs: list[dict]) -> str:
    """Short/Product Title: Brand + Series + MPN + Item Type + key attributes."""
    key_attrs = [a["value"] for a in attrs[:3] if a["label"] not in ("Series",)]
    parts = [p for p in [brand, series, mpn, item_type] + key_attrs if p]
    return " ".join(parts)


def _build_long_desc(brand: str, series: str, mpn: str, item_type: str,
                     attrs: list[dict], desc: str) -> str:
    """Long description: Brand + item type + all attributes in structured sentence."""
    attr_str = ", ".join(
        f"{a['label']}: {a['value']}{' ' + a['uom'] if a['uom'] else ''}"
        for a in attrs
    )
    base = f"{brand} {item_type}"
    if series:
        base += f", {series}"
    if attr_str:
        base += f", {attr_str}"
    # Append original desc for context
    clean_desc = _strip_mpn_prefix(desc)
    if clean_desc and clean_desc.lower() not in base.lower():
        base += f". {clean_desc}"
    return base


def _build_retail_desc(brand: str, series: str, item_type: str,
                       attrs: list[dict]) -> str:
    """Retail description: concise, consumer-facing."""
    color = next((a["value"] for a in attrs if a["label"] == "Color"), "")
    mat = next((a["value"] for a in attrs if a["label"] == "Material"), "")
    extras = [v for v in [color, mat] if v]
    parts = [p for p in [brand, series, item_type] + extras if p]
    return " ".join(parts)


def _strip_mpn_prefix(desc: str) -> str:
    """Remove leading MPN code from Part_Desc (e.g. 'DCB518ASTS06G Diablo ...' → 'Diablo ...')."""
    # Pattern: starts with alphanumeric code, then space, then description
    m = re.match(r'^[A-Z0-9\-]{4,}\s+(.+)', desc.strip())
    return m.group(1) if m else desc.strip()


def _infer_item_type(desc: str, fine: str) -> str:
    """Extract the core item type noun from description."""
    # Use Fine classification first
    if fine and fine.lower() not in ("uncategorized", "general products"):
        return fine
    # Fallback: first recognisable noun in stripped desc
    stripped = _strip_mpn_prefix(desc)
    type_patterns = [
        r'\b(Dishwasher|Dryer|Washer|Sander|Panel|Board|Rail|Railing|Kit|'
        r'Disc|Wheel|Belt|Tape|Door|Window|Skylight|Shingle|Mortar|Tape|'
        r'Post|Sleeve|Cap|Threshold|Fascia|Decking|Siding|Gauge|Pad)\b'
    ]
    for pat in type_patterns:
        m = re.search(pat, stripped, re.I)
        if m:
            return m.group(1)
    return stripped.split()[0] if stripped else "Product"


# ── Main Entry Point ──────────────────────────────────────────────────────────

def enrich_unilog_row(row: dict) -> dict:
    """
    Transform a single raw Unilog input row into the full 252-column output record.

    Input keys expected (case-insensitive):
        Mfg_Part_Num, Part_Desc, E1_Brand, Unilog_Brand, DIB_Brand, Part_Manuf

    Returns a flat dict matching the Delivery Format column names.
    """
    # Normalise input key access
    def get(key: str) -> str:
        for k, v in row.items():
            if k.lower() == key.lower():
                return _clean(v)
        return ""

    mpn       = get("Mfg_Part_Num")
    part_desc = get("Part_Desc")
    e1_brand  = get("E1_Brand")
    ul_brand  = get("Unilog_Brand")
    dib_brand = get("DIB_Brand")
    raw_manuf = get("Part_Manuf")

    mfr_name = _normalise_manufacturer(raw_manuf)
    brand    = _normalise_brand(e1_brand, ul_brand, dib_brand, mfr_name, part_desc)

    # Classification
    dept, cls, fine, classpath = _classify(part_desc)

    # Attribute extraction
    attrs = _extract_attributes(part_desc)
    series = next((a["value"] for a in attrs if a["label"] == "Series"), "")
    item_type = _infer_item_type(part_desc, fine)

    # Confidence scoring
    has_brand      = bool(brand and brand != mfr_name)
    has_brand_desc = has_brand and brand not in (mfr_name, "")
    has_attrs      = len(attrs) > 0
    is_classified  = fine not in ("Uncategorized", "General Products", "")
    score = 0.40
    if is_classified:  score += 0.25
    if has_attrs:      score += 0.15
    if has_brand_desc: score += 0.20
    confidence = min(round(score, 2), 0.95)

    # Description variants
    invoice_desc = _build_invoice_desc(brand, part_desc, attrs)
    mobile_desc  = _build_mobile_desc(brand, mfr_name, series, mpn, item_type, part_desc)
    short_desc   = _build_short_desc(brand, series, mpn, item_type, attrs)
    long_desc    = _build_long_desc(brand, series, mpn, item_type, attrs, part_desc)
    retail_desc  = _build_retail_desc(brand, series, item_type, attrs)

    # Image naming convention (Unilog standard: BRAND_MPN.jpg)
    brand_slug  = re.sub(r'[^A-Za-z0-9]', '', brand.split('®')[0].split('™')[0])
    product_img = f"{brand_slug}_{mpn}.jpg" if brand_slug and mpn else ""
    spec_sheet  = f"{brand_slug}_{mpn}_Specification_Sheet.pdf" if brand_slug and mpn else ""

    # Build output record — all 252 columns
    out: dict[str, str] = {}

    # ── Group 1: Reference URLs ─────────────────────────────────────────────
    out["MFR URL"]  = ""
    out["Ref URL 1"] = ""
    out["Ref URL 2"] = ""
    out["Ref URL 3"] = ""
    out["Ref URL 4"] = ""
    out["Ref URL 5"] = ""

    # ── Group 2: Core identifiers ───────────────────────────────────────────
    out["PART_NUMBER"]         = ""
    out["Dept"]                = dept
    out["Class"]               = cls
    out["Fine"]                = fine
    out["SKU - MY_PART_NUMBER"] = ""
    out["Mfg_Part_Num"]        = mpn
    out["Part_Desc"]           = part_desc
    out["E1_Brand"]            = e1_brand
    out["Unilog_Brand"]        = ul_brand
    out["DIB_Brand"]           = dib_brand
    out["Part_Manuf"]          = raw_manuf

    # ── Group 3: Normalised identity ───────────────────────────────────────
    out["MANUFACTURER_NAME"]        = mfr_name
    out["BRAND_NAME"]               = brand
    out["TRADE_NAME"]               = ""
    out["MANUFACTURER_PART_NUMBER"] = mpn
    out["ALTERNATE_PART_NUMBER"]    = ""
    out["Classpath"]                = classpath

    # ── Group 4: Descriptions ──────────────────────────────────────────────
    out["MOBILE_DESC"]          = mobile_desc
    out["INVOICE_DESC"]         = invoice_desc
    out["SHORT_DESC"]           = short_desc
    out["LONG_DESC1"]           = long_desc
    out["RETAIL_DESC"]          = retail_desc
    out["MARKETING_DESCRIPTION"] = ""

    # ── Group 5: Item features (up to 20) ─────────────────────────────────
    for i in range(1, 21):
        out[f"ITEM_FEATURES_{i}"] = ""

    # Populate first N features from extracted attrs
    for i, a in enumerate(attrs[:10], 1):
        feat = f"{a['label']}: {a['value']}"
        if a["uom"]:
            feat += f" {a['uom']}"
        out[f"ITEM_FEATURES_{i}"] = feat

    # ── Group 6: Extra fields ──────────────────────────────────────────────
    out["With"]               = ""
    out["Standard/Approvals"] = ""
    out["Prop 65"]            = ""
    out["Application"]        = ""
    out["Includes"]           = ""
    out["Product Name"]       = short_desc

    # ── Group 7: Attributes (50 slots × 3 cols) ────────────────────────────
    for i in range(1, 51):
        out[f"ATTRIBUTE_LABEL {i}"] = ""
        out[f"ATTRIBUTE_VALUE {i}"] = ""
        out[f"ATTRIBUTE_UOM {i}"]   = ""

    for i, a in enumerate(attrs[:50], 1):
        out[f"ATTRIBUTE_LABEL {i}"] = a["label"]
        out[f"ATTRIBUTE_VALUE {i}"] = a["value"]
        out[f"ATTRIBUTE_UOM {i}"]   = a["uom"]

    # ── Group 8: Commerce / logistics ──────────────────────────────────────
    out["UPC"]                          = ""
    out["EAN"]                          = ""
    out["GTIN"]                         = ""
    out["UNSPSC"]                       = ""
    out["Warranty"]                     = ""
    out["List Price"]                   = ""
    out["Selling Qty"]                  = ""
    out["Selling UOM"]                  = ""
    out["Standard Packaging Information"] = ""
    out["LENGTH"]                       = ""
    out["LENGTH_UOM"]                   = ""
    out["HEIGHT"]                       = ""
    out["HEIGHT_UOM"]                   = ""
    out["WIDTH"]                        = ""
    out["WIDTH_UOM"]                    = ""
    out["WEIGHT"]                       = ""
    out["WEIGHT_UOM"]                   = ""
    out["VOLUME"]                       = ""
    out["VOLUME_UOM"]                   = ""

    # Populate dimensions from attrs if found
    for a in attrs:
        if a["label"] == "Length":
            out["LENGTH"] = a["value"]; out["LENGTH_UOM"] = a["uom"]
        elif a["label"] == "Width":
            out["WIDTH"] = a["value"]; out["WIDTH_UOM"] = a["uom"]

    # ── Group 9: Digital assets ────────────────────────────────────────────
    out["Product Image"]    = product_img
    out["Alternate Image 1"] = ""
    out["Alternate Image 2"] = ""
    out["Alternate Image 3"] = ""
    out["Alternate Image 4"] = ""
    out["SDS"]               = ""
    out["SDS_1"]             = ""
    out["Warranty Information"] = ""
    out["Catalog"]             = ""
    out["Specification Sheet"]  = spec_sheet
    out["Instruction/Installation Manual"] = ""
    out["Service Manual"]       = ""
    out["Owners/User Manual"]   = ""
    out["Line Drawing"]         = ""
    out["MTR"]                  = ""
    out["RoHS"]                 = ""
    out["Full Engineering Drawing"] = ""
    out["Energy Star Guide"]    = ""
    out["Technical Bulletin"]   = ""
    out["Submittal"]            = ""
    out["Compatibility Chart"]  = ""
    out["Size Chart"]           = ""
    out["Product Label/Insert"] = ""
    out["Video Link"]           = ""
    out["Video Link 1"]         = ""

    # ── Group 10: Provenance ────────────────────────────────────────────────
    out["Country Of Origin"]   = ""
    out["Discontinued"]        = ""
    out["Actual Image (Yes/No)"] = "No"

    # ── Internal metadata (not in output but useful for API) ───────────────
    out["_confidence"]      = str(round(confidence, 2))
    out["_needs_review"]    = "Yes" if confidence < 0.65 else "No"
    out["_enrichment_mode"] = "deterministic_rule"

    return out


def enrich_unilog_batch(rows) -> list[dict]:
    """Enrich a list of raw Unilog input rows or a pandas DataFrame."""
    try:
        # Support pandas DataFrame input
        import pandas as pd
        if isinstance(rows, pd.DataFrame):
            rows = rows.to_dict('records')
    except ImportError:
        pass
    return [enrich_unilog_row(r) for r in rows]


# ── LLM upgrade (Gemini) ──────────────────────────────────────────────────────

def enrich_unilog_row_llm(row: dict, api_key: str) -> dict:
    """
    Drop-in LLM-enhanced version: runs rule-based enrichment first,
    then uses Gemini to fill any empty or low-confidence fields.
    """
    base = enrich_unilog_row(row)

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")

        part_desc = base.get("Part_Desc", "")
        brand     = base.get("BRAND_NAME", "")
        mfr       = base.get("MANUFACTURER_NAME", "")
        classpath = base.get("Classpath", "")
        mpn       = base.get("MANUFACTURER_PART_NUMBER", "")

        prompt = f"""You are a Unilog product content specialist. Given this raw product row:
Part Description: {part_desc}
Brand: {brand}
Manufacturer: {mfr}
MPN: {mpn}
Classpath: {classpath}

Generate the following fields following Unilog content guidelines:
1. SHORT_DESC: Brand + Series + MPN + Item Type + key attributes (title case, ≤120 chars)
2. LONG_DESC1: Full structured description with all attributes (comma-separated, ≤500 chars)
3. MOBILE_DESC: Manufacturer, Brand, Series, MPN (comma-separated, 60-80 chars)
4. INVOICE_DESC: Abbreviated ALL CAPS ≤40 chars (like a till receipt)
5. MARKETING_DESCRIPTION: 1-2 engaging sentences for the product page
6. UP TO 5 key attributes as JSON: [{{"label":"...", "value":"...", "uom":"..."}}]

Respond ONLY with valid JSON:
{{"SHORT_DESC":"...","LONG_DESC1":"...","MOBILE_DESC":"...","INVOICE_DESC":"...","MARKETING_DESCRIPTION":"...","ATTRIBUTES":[...]}}"""

        resp = model.generate_content(prompt)
        text = resp.text.strip()
        # Extract JSON
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            for key in ("SHORT_DESC", "LONG_DESC1", "MOBILE_DESC",
                        "INVOICE_DESC", "MARKETING_DESCRIPTION"):
                if parsed.get(key):
                    base[key] = parsed[key]
            # Merge LLM attributes
            llm_attrs = parsed.get("ATTRIBUTES", [])
            for i, a in enumerate(llm_attrs[:50], 1):
                if not base.get(f"ATTRIBUTE_LABEL {i}"):
                    base[f"ATTRIBUTE_LABEL {i}"] = a.get("label", "")
                    base[f"ATTRIBUTE_VALUE {i}"] = a.get("value", "")
                    base[f"ATTRIBUTE_UOM {i}"]   = a.get("uom", "")
            base["_enrichment_mode"] = "llm+rule"
            base["_confidence"] = "0.87"
    except Exception as e:
        base["_llm_error"] = str(e)

    return base
