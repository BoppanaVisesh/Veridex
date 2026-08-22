"""
Veridex NBA Platform — Realistic Synthetic Seed Data (§12, §13)

Generates realistic Product Intelligence and Catalog domain seed data for all 9 decision types:
- Products with technical attributes, completeness metrics, validation status
- Suppliers and Ingestion Batch Feeds with quality ratios
- Marketplace Channels with syndication requirements and taxonomy rules
- ISO/UL and safety compliance certification registries
- Historical outcome records (225 total) for warm-starting the Brier calibration and EMA learning loops

Distribution of 225 historical records across D1-D9:
  D1: 35 | D2: 25 | D3: 25 | D4: 20 | D5: 35 | D6: 20 | D7: 30 | D8: 20 | D9: 15
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from backend.models import (
    Fact, EntityType, PIIClass, DecisionType, DecisionRequest,
    Outcome, HumanDecision
)


# ── Entity Data (Product Intelligence Domain) ─────────────────────────────────

PRODUCTS_SEED = [
    {"id": "propump-5000", "name": "ProPump 5000 Commercial Water Pump", "category": "Industrial Pumps", "status": "draft", "completeness": 45.0, "price": 1250.00, "supplier": "SUP-001"},
    {"id": "apex-turbine-tx1", "name": "Apex Turbine TX-1", "category": "Power Generation", "status": "validated", "completeness": 92.0, "price": 4850.00, "supplier": "SUP-002"},
    {"id": "hydroflow-hf2", "name": "HydroFlow HF-2 Pressure Regulator", "category": "Fluid Control", "status": "conflicted", "completeness": 68.0, "price": 620.00, "supplier": "SUP-003"},
    {"id": "solarpower-sp200", "name": "SolarPower SP-200 Hybrid Inverter", "category": "Solar & Renewable", "status": "validated", "completeness": 88.0, "price": 1890.00, "supplier": "SUP-004"},
    {"id": "ecoflow-ef300", "name": "EcoFlow EF-300 Solar Pump", "category": "Pumps & Irrigation", "status": "draft", "completeness": 35.0, "price": 890.00, "supplier": "SUP-001"},
    {"id": "titan-valve-v10", "name": "Titan Flow Valve V-10", "category": "Valves & Actuators", "status": "validated", "completeness": 94.0, "price": 340.00, "supplier": "SUP-005"},
    {"id": "industrial-pump-hd", "name": "Industrial Heavy Duty Water Pump", "category": "Industrial Pumps", "status": "needs_review", "completeness": 60.0, "price": 2100.00, "supplier": "SUP-003"},
    {"id": "thermocool-tc100", "name": "ThermoCool TC-100 Heat Exchanger", "category": "HVAC & Cooling", "status": "validated", "completeness": 98.0, "price": 3150.00, "supplier": "SUP-002"},
    {"id": "voltsensor-vs50", "name": "VoltSensor VS-50 Smart Probe", "category": "Sensors & Measurement", "status": "flagged", "completeness": 72.0, "price": 185.00, "supplier": "SUP-006"},
    {"id": "flexicon-conveyor-c4", "name": "Flexicon Conveyor Roller C4", "category": "Material Handling", "status": "validated", "completeness": 85.0, "price": 750.00, "supplier": "SUP-005"},
]

SUPPLIERS_SEED = [
    {"id": "SUP-001", "name": "Global Pump Supplies Ltd", "feed_id": "supplier_batch_feed_04", "validation_rate": 0.68, "batch_syntax_errors": 6},
    {"id": "SUP-002", "name": "Apex Engineering Group", "feed_id": "apex_feed_ingest_v2", "validation_rate": 0.94, "batch_syntax_errors": 1},
    {"id": "SUP-003", "name": "HydroFlow Manufacturing Co", "feed_id": "hydroflow_direct_xml", "validation_rate": 0.76, "batch_syntax_errors": 4},
    {"id": "SUP-004", "name": "SolarTech Global Feeds", "feed_id": "solartech_csv_batch_01", "validation_rate": 0.89, "batch_syntax_errors": 2},
    {"id": "SUP-005", "name": "Titan Industrial Components", "feed_id": "titan_edi_feed_08", "validation_rate": 0.96, "batch_syntax_errors": 0},
    {"id": "SUP-006", "name": "Precision Sensor Systems", "feed_id": "sensor_json_stream_v1", "validation_rate": 0.82, "batch_syntax_errors": 3},
]

CHANNELS_SEED = [
    {"id": "CHN-01", "name": "Amazon Business B2B", "min_completeness": 90.0, "mandatory_fields": ["brand", "price", "weight", "dimensions", "category"]},
    {"id": "CHN-02", "name": "Grainger Industrial Supply", "min_completeness": 95.0, "mandatory_fields": ["brand", "model", "certification", "specs"]},
    {"id": "CHN-03", "name": "Fastenal Direct", "min_completeness": 85.0, "mandatory_fields": ["sku", "material", "voltage", "price"]},
    {"id": "CHN-04", "name": "Ferguson Wholesale", "min_completeness": 88.0, "mandatory_fields": ["brand", "dimensions", "flow_rate", "warranty"]},
]

TENANT_ID = "catalog-prod-001"


def _now() -> datetime:
    return datetime.utcnow()


def _past(days: int) -> datetime:
    return datetime.utcnow() - timedelta(days=days)


# ── Fact Generation Functions (Product Domain) ────────────────────────────────

def generate_crm_facts(entity_id: str, entity_type_str: str) -> list[Fact]:
    """Generate Catalog Database facts for a product or category entity."""
    facts = []
    prod = next((p for p in PRODUCTS_SEED if p["id"] == entity_id), None)
    if prod:
        facts.extend([
            Fact(
                tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id=entity_id,
                fact_type="product_status", value=prod["status"],
                source_agent="Catalog_Evidence_Agent", confidence=0.98, timestamp=_past(0),
                evidence_ref=f"Catalog Database Record #{entity_id}",
            ),
            Fact(
                tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id=entity_id,
                fact_type="field_completeness_pct", value=prod["completeness"],
                source_agent="Catalog_Evidence_Agent", confidence=0.95, timestamp=_past(0),
                evidence_ref=f"Catalog Completeness Metric #{entity_id}",
            ),
            Fact(
                tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id=entity_id,
                fact_type="category_value", value=prod["category"],
                source_agent="Catalog_Evidence_Agent", confidence=0.90, timestamp=_past(0),
                evidence_ref=f"Product Taxonomy Index #{entity_id}",
            ),
        ])
    else:
        # Generic product facts
        facts.append(
            Fact(
                tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id=entity_id,
                fact_type="product_status", value="draft",
                source_agent="Catalog_Evidence_Agent", confidence=0.85, timestamp=_past(1),
                evidence_ref=f"Catalog Database Record #{entity_id}",
            )
        )
    return facts


def generate_email_facts(entity_id: str, scenario: str = "positive") -> list[Fact]:
    """Generate Supplier Ingestion communication signals."""
    facts = []
    if scenario == "positive":
        facts.append(
            Fact(
                tenant_id=TENANT_ID, entity_type=EntityType.SOURCE, entity_id=entity_id,
                fact_type="supplier_communication_signal",
                value="Supplier feed verified — manufacturer confirmed specification updates for upcoming Q3 catalog release.",
                source_agent="Email_Agent", confidence=0.88, timestamp=_past(1),
                evidence_ref=f"Supplier Ingest Feed Log: {entity_id}",
            )
        )
    else:
        facts.append(
            Fact(
                tenant_id=TENANT_ID, entity_type=EntityType.SOURCE, entity_id=entity_id,
                fact_type="supplier_communication_signal",
                value="Vendor feed notification: conflicting operating voltage and missing certifications in batch payload.",
                source_agent="Email_Agent", confidence=0.82, timestamp=_past(1),
                evidence_ref=f"Supplier Ingest Notification: {entity_id}",
            )
        )
    return facts


def generate_activity_facts(entity_id: str, pattern: str = "normal") -> list[Fact]:
    """Generate Validation Engine facts."""
    return [
        Fact(
            tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id=entity_id,
            fact_type="specs_validation_status",
            value="validation_complete_nominal" if pattern == "normal" else "flagged_spec_inconsistency",
            source_agent="Candidate_Activity_Agent", confidence=0.92, timestamp=_past(0),
            evidence_ref=f"Validation Engine Report #{entity_id}",
        ),
        Fact(
            tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id=entity_id,
            fact_type="days_since_validation", value=14 if pattern == "normal" else 45,
            source_agent="Candidate_Activity_Agent", confidence=0.95, timestamp=_past(0),
            evidence_ref=f"Validation Audit Timestamp #{entity_id}",
        ),
    ]


def generate_compliance_facts(entity_id: str, comp_status: str = "cleared") -> list[Fact]:
    """Generate Compliance Registry facts."""
    is_blocked = (comp_status != "cleared")
    return [
        Fact(
            tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id=entity_id,
            fact_type="certification_status", value="verified" if not is_blocked else "missing",
            source_agent="Compliance_Registry_Agent", confidence=0.99, timestamp=_past(0),
            evidence_ref=f"Compliance Registry Audit #{entity_id}",
        ),
        Fact(
            tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id=entity_id,
            fact_type="is_compliance_blocked", value=is_blocked,
            source_agent="Compliance_Registry_Agent", confidence=0.99, timestamp=_past(0),
            evidence_ref=f"Compliance Block Gate #{entity_id}",
        ),
    ]


def generate_market_facts(entity_id: str, category: str = "Industrial Pumps") -> list[Fact]:
    """Generate Marketplace Feed & Syndication facts."""
    return [
        Fact(
            tenant_id=TENANT_ID, entity_type=EntityType.CATEGORY, entity_id=category,
            fact_type="comparable_products_count", value=8,
            source_agent="Market_Data_Agent", confidence=0.88, timestamp=_past(1),
            evidence_ref=f"Marketplace Category Feed: {category}",
        ),
        Fact(
            tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id=entity_id,
            fact_type="price_confidence", value=0.92,
            source_agent="Market_Data_Agent", confidence=0.90, timestamp=_past(1),
            evidence_ref=f"Price Benchmark Feed #{entity_id}",
        ),
    ]


# ── Decision Scenario Generators (D1–D9) ──────────────────────────────────────

def generate_d1_scenario() -> dict[str, Any]:
    """D1: Listing Readiness Risk — product aging unlisted with incomplete data."""
    return {
        "decision": DecisionRequest(
            decision_id="DEC-D1-001",
            tenant_id=TENANT_ID,
            decision_type=DecisionType.D1,
            primary_entity_type=EntityType.PRODUCT,
            primary_entity_id="propump-5000",
            requested_by="CAT-OPS-01",
            description="Product 'propump-5000' (ProPump 5000) is aging (14 days unlisted) with only 45% completeness and 2 flagged fields before channel launch deadline.",
            urgency_score=0.88,
        ),
        "facts": [
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="propump-5000",
                 fact_type="product_status", value="draft", source_agent="Catalog_Evidence_Agent",
                 confidence=0.99, timestamp=_past(0), evidence_ref="Catalog DB: propump-5000 status=draft"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="propump-5000",
                 fact_type="product_missing_flagged_count", value=4, source_agent="Catalog_Evidence_Agent",
                 confidence=0.95, timestamp=_past(0), evidence_ref="Catalog ProductFields status: 2 missing, 2 flagged"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="propump-5000",
                 fact_type="field_completeness_pct", value=45.0, source_agent="Catalog_Evidence_Agent",
                 confidence=0.95, timestamp=_past(0), evidence_ref="Catalog Completeness Index: 45.0%"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="propump-5000",
                 fact_type="product_age_days", value=14, source_agent="Catalog_Evidence_Agent",
                 confidence=0.99, timestamp=_past(0), evidence_ref="Ingest timestamp: 14 days ago"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="propump-5000",
                 fact_type="certification_status", value="valid", source_agent="Compliance_Registry_Agent",
                 confidence=0.95, timestamp=_past(0), evidence_ref="UL/CSA Safety Registry: UL-60335 compliant"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="propump-5000",
                 fact_type="price_confidence", value=0.85, source_agent="Market_Data_Agent",
                 confidence=0.88, timestamp=_past(0), evidence_ref="Supplier wholesale price verified at $1,250.00"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="propump-5000",
                 fact_type="specs_validation_status", value="flagged_fields_present", source_agent="Candidate_Activity_Agent",
                 confidence=0.92, timestamp=_past(0), evidence_ref="Validation Engine: Flow rate and operating voltage flagged"),
        ],
    }


def generate_d2_scenario() -> dict[str, Any]:
    """D2: Category/Channel Placement — best taxonomy and sales channel placement."""
    return {
        "decision": DecisionRequest(
            decision_id="DEC-D2-001",
            tenant_id=TENANT_ID,
            decision_type=DecisionType.D2,
            primary_entity_type=EntityType.PRODUCT,
            primary_entity_id="apex-turbine-tx1",
            requested_by="CAT-OPS-02",
            description="Determine optimal catalog category and channel placement for Apex Turbine TX-1 based on validated high-voltage and turbine specifications.",
            urgency_score=0.65,
        ),
        "facts": [
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="apex-turbine-tx1",
                 fact_type="category_value", value="Industrial Power Generation > Turbines", source_agent="Knowledge_Base_Agent",
                 confidence=0.88, timestamp=_past(1), evidence_ref="Taxonomy Engine: Recommended category match score 0.88"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="apex-turbine-tx1",
                 fact_type="category_confidence", value=0.88, source_agent="Knowledge_Base_Agent",
                 confidence=0.92, timestamp=_past(1), evidence_ref="Taxonomy Confidence Matrix"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="apex-turbine-tx1",
                 fact_type="comparable_products_count", value=12, source_agent="Market_Data_Agent",
                 confidence=0.85, timestamp=_past(2), evidence_ref="Catalog Category Index: 12 peer turbine products"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="apex-turbine-tx1",
                 fact_type="taxonomy_completeness", value=92.0, source_agent="Knowledge_Base_Agent",
                 confidence=0.95, timestamp=_past(0), evidence_ref="Attribute mapping: 18/20 required category attributes present"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="apex-turbine-tx1",
                 fact_type="material_spec", value="Reinforced Titanium Alloy Housing", source_agent="Knowledge_Base_Agent",
                 confidence=0.90, timestamp=_past(0), evidence_ref="Engineering Spec Sheet #TX1-2026"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="apex-turbine-tx1",
                 fact_type="channel_compliance_rules", value="Meets Amazon B2B & Grainger Heavy Equipment standards", source_agent="Compliance_Registry_Agent",
                 confidence=0.94, timestamp=_past(0), evidence_ref="Syndication Channel Rules Engine"),
        ],
    }


def generate_d3_scenario() -> dict[str, Any]:
    """D3: Data Decay Risk — product data going stale or contradicted by newer supplier updates."""
    return {
        "decision": DecisionRequest(
            decision_id="DEC-D3-001",
            tenant_id=TENANT_ID,
            decision_type=DecisionType.D3,
            primary_entity_type=EntityType.PRODUCT,
            primary_entity_id="hydroflow-hf2",
            requested_by="CAT-OPS-01",
            description="Product 'hydroflow-hf2' shows data decay: conflicting operating voltage (110V vs 220V) between vendor upload batches and last validation was 45 days ago.",
            urgency_score=0.85,
        ),
        "facts": [
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="hydroflow-hf2",
                 fact_type="newest_evidence_age_days", value=45, source_agent="Market_Data_Agent",
                 confidence=0.95, timestamp=_past(45), evidence_ref="Newest supplier ingest timestamp: 45 days ago"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="hydroflow-hf2",
                 fact_type="conflicted_fields_count", value=2, source_agent="Candidate_Activity_Agent",
                 confidence=0.92, timestamp=_past(0), evidence_ref="Contradiction Detector: operating_voltage (110V vs 220V), max_pressure (150 vs 200 PSI)"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="hydroflow-hf2",
                 fact_type="days_since_validation", value=45, source_agent="Candidate_Activity_Agent",
                 confidence=0.98, timestamp=_past(0), evidence_ref="Validation Engine: Last audit executed 45 days ago"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="hydroflow-hf2",
                 fact_type="source_evidence_spread", value="Conflicting values between supplier_batch_01.csv and vendor_update_04.xml", source_agent="Market_Data_Agent",
                 confidence=0.88, timestamp=_past(0), evidence_ref="Provenance Audit Trail"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="hydroflow-hf2",
                 fact_type="pricing_freshness", value="Price last updated 60 days ago ($620.00)", source_agent="Email_Agent",
                 confidence=0.80, timestamp=_past(60), evidence_ref="Pricing catalog feed"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="hydroflow-hf2",
                 fact_type="certification_expiry", value="ISO-9001 audit valid through 2027", source_agent="Compliance_Registry_Agent",
                 confidence=0.95, timestamp=_past(0), evidence_ref="Compliance Registry Entry #ISO-HF2"),
        ],
    }


def generate_d4_scenario() -> dict[str, Any]:
    """D4: Re-validation Cycle — product data due for periodic re-verification."""
    return {
        "decision": DecisionRequest(
            decision_id="DEC-D4-001",
            tenant_id=TENANT_ID,
            decision_type=DecisionType.D4,
            primary_entity_type=EntityType.PRODUCT,
            primary_entity_id="solarpower-sp200",
            requested_by="CAT-OPS-03",
            description="SolarPower SP-200 inverter is due for periodic 90-day re-validation audit. 1 attribute flagged for potential spec drift.",
            urgency_score=0.60,
        ),
        "facts": [
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="solarpower-sp200",
                 fact_type="days_since_last_cycle", value=92, source_agent="Candidate_Activity_Agent",
                 confidence=0.99, timestamp=_past(0), evidence_ref="Audit Scheduler: 92 days elapsed since last full validation"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="solarpower-sp200",
                 fact_type="field_confidence_distribution", value="Mean confidence 0.82; 1 field below 0.60", source_agent="Candidate_Activity_Agent",
                 confidence=0.90, timestamp=_past(0), evidence_ref="Confidence Distribution Matrix"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="solarpower-sp200",
                 fact_type="flagged_fields_count", value=1, source_agent="Candidate_Activity_Agent",
                 confidence=0.95, timestamp=_past(0), evidence_ref="Validation Engine: peak_efficiency_pct flagged for re-test"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="solarpower-sp200",
                 fact_type="supplier_catalog_update", value="Supplier released Q2 firmware update with revised specs", source_agent="Email_Agent",
                 confidence=0.85, timestamp=_past(5), evidence_ref="Supplier Bulletin #SP200-FW2"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="solarpower-sp200",
                 fact_type="regulatory_audit_schedule", value="IEEE-1547 Grid Interconnection standard due for renewal in 45 days", source_agent="Compliance_Registry_Agent",
                 confidence=0.95, timestamp=_past(0), evidence_ref="Grid Interconnect Registry"),
        ],
    }


def generate_d5_scenario() -> dict[str, Any]:
    """D5: Incomplete Listing Promotion — prioritize high-demand incomplete product for enrichment."""
    return {
        "decision": DecisionRequest(
            decision_id="DEC-D5-001",
            tenant_id=TENANT_ID,
            decision_type=DecisionType.D5,
            primary_entity_type=EntityType.PRODUCT,
            primary_entity_id="ecoflow-ef300",
            requested_by="CAT-OPS-01",
            description="EcoFlow EF-300 Solar Pump has high search demand but low completeness (35%). Run prioritized 3-tier enrichment to unblock publication.",
            urgency_score=0.75,
        ),
        "facts": [
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="ecoflow-ef300",
                 fact_type="field_completeness_pct", value=35.0, source_agent="CRM_ATS_Agent",
                 confidence=0.98, timestamp=_past(0), evidence_ref="Catalog Completeness Index: 35.0% (7/20 fields present)"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="ecoflow-ef300",
                 fact_type="missing_fields_count", value=13, source_agent="CRM_ATS_Agent",
                 confidence=0.98, timestamp=_past(0), evidence_ref="Missing required fields: flow_rate, max_head, operating_temp, warranty, weight, etc."),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="ecoflow-ef300",
                 fact_type="enrichment_success_ratio", value=0.85, source_agent="Knowledge_Base_Agent",
                 confidence=0.88, timestamp=_past(0), evidence_ref="Enrichment Engine: 3-tier pipeline historical yield on solar pumps is 85%"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="ecoflow-ef300",
                 fact_type="context_text_availability", value="High quality manufacturer PDF data sheet uploaded (12KB text extracted)", source_agent="CRM_ATS_Agent",
                 confidence=0.94, timestamp=_past(0), evidence_ref="Raw Ingest Document: ecoflow_ef300_datasheet.pdf"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="ecoflow-ef300",
                 fact_type="mandatory_attributes_status", value="Missing 3 mandatory marketplace fields", source_agent="Compliance_Registry_Agent",
                 confidence=0.96, timestamp=_past(0), evidence_ref="Amazon B2B Mandatory Schema Checklist"),
        ],
    }


def generate_d6_scenario() -> dict[str, Any]:
    """D6: Source Reliability Health — supplier upload feed with declining validation ratio."""
    return {
        "decision": DecisionRequest(
            decision_id="DEC-D6-001",
            tenant_id=TENANT_ID,
            decision_type=DecisionType.D6,
            primary_entity_type=EntityType.SOURCE,
            primary_entity_id="supplier_batch_feed_04",
            requested_by="CAT-OPS-02",
            description="Supplier feed 'supplier_batch_feed_04' (Global Pump Supplies) shows declining data reliability: 42% validation ratio and 8 syntax rejections in latest batch.",
            urgency_score=0.78,
        ),
        "facts": [
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.SOURCE, entity_id="supplier_batch_feed_04",
                 fact_type="source_label", value="Global Pump Supplies Feed v4", source_agent="Market_Data_Agent",
                 confidence=0.99, timestamp=_past(0), evidence_ref="Supplier Ingest Registry #SUP-001"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.SOURCE, entity_id="supplier_batch_feed_04",
                 fact_type="source_validation_ratio", value=0.42, source_agent="Market_Data_Agent",
                 confidence=0.95, timestamp=_past(0), evidence_ref="Ingest Batch Audit #B-409: 21/50 fields passed validation (42%)"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.SOURCE, entity_id="supplier_batch_feed_04",
                 fact_type="source_historical_trend", value="Validation ratio dropped from 85% to 42% over last 3 upload batches", source_agent="Market_Data_Agent",
                 confidence=0.90, timestamp=_past(0), evidence_ref="Historical Ingest Trend Log"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.SOURCE, entity_id="supplier_batch_feed_04",
                 fact_type="syntax_failure_rate", value=0.38, source_agent="Market_Data_Agent",
                 confidence=0.92, timestamp=_past(0), evidence_ref="Parser Syntax Rejections: 19 invalid numeric strings, unescaped commas"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.SOURCE, entity_id="supplier_batch_feed_04",
                 fact_type="source_compliance_violations", value=3, source_agent="Compliance_Registry_Agent",
                 confidence=0.98, timestamp=_past(0), evidence_ref="Regulatory parser: 3 missing mandatory energy efficiency disclosures"),
        ],
    }


def generate_d7_scenario() -> dict[str, Any]:
    """D7: Certification/Compliance Gap — unverified marketing claim triggering compliance veto."""
    return {
        "decision": DecisionRequest(
            decision_id="DEC-D7-001",
            tenant_id=TENANT_ID,
            decision_type=DecisionType.D7,
            primary_entity_type=EntityType.PRODUCT,
            primary_entity_id="industrial-pump-hd",
            requested_by="CAT-OPS-01",
            description="Industrial Heavy Duty Water Pump is missing verified ISO/UL certification. Marketing term 'Heavy Duty' does not prove certification. Compliance veto required.",
            urgency_score=0.95,
        ),
        "facts": [
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="industrial-pump-hd",
                 fact_type="certification_value", value="Unknown", source_agent="Compliance_Registry_Agent",
                 confidence=0.0, timestamp=_past(0), evidence_ref="Catalog DB Field 'certification': value=Unknown, status=NEEDS_REVIEW. Inferred from 'Heavy Duty' marketing term (unverified)"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="industrial-pump-hd",
                 fact_type="certification_status", value="missing", source_agent="Compliance_Registry_Agent",
                 confidence=0.98, timestamp=_past(0), evidence_ref="Compliance Registry: No accredited ISO 9001 or UL certificate on file"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="industrial-pump-hd",
                 fact_type="certification_confidence", value=0.0, source_agent="Compliance_Registry_Agent",
                 confidence=0.99, timestamp=_past(0), evidence_ref="Anti-hallucination guardrail: confidence=0.0 for unverified claims"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="industrial-pump-hd",
                 fact_type="is_compliance_blocked", value=True, source_agent="Compliance_Registry_Agent",
                 confidence=0.99, timestamp=_past(0), evidence_ref="Compliance Engine Hard Block: Unverified safety certification"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="industrial-pump-hd",
                 fact_type="safety_standards_mapping", value="Requires UL 778 standard for motor-operated water pumps", source_agent="Compliance_Registry_Agent",
                 confidence=0.95, timestamp=_past(0), evidence_ref="Mandatory Commercial Safety Standard UL-778"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="industrial-pump-hd",
                 fact_type="supplier_accreditation_proof", value="Supplier has not uploaded accredited laboratory test report", source_agent="Compliance_Registry_Agent",
                 confidence=0.95, timestamp=_past(0), evidence_ref="Supplier Document Repository"),
        ],
    }


def generate_d8_scenario() -> dict[str, Any]:
    """D8: Publish-Confidence Threshold — evaluate field-level confidence threshold."""
    return {
        "decision": DecisionRequest(
            decision_id="DEC-D8-001",
            tenant_id=TENANT_ID,
            decision_type=DecisionType.D8,
            primary_entity_type=EntityType.PRODUCT,
            primary_entity_id="titan-valve-v10",
            requested_by="CAT-OPS-03",
            description="Evaluate publish gate for critical attribute 'max_pressure_psi' on Titan Flow Valve V-10. Field confidence 0.94 meets automated publish criteria.",
            urgency_score=0.55,
        ),
        "facts": [
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="titan-valve-v10",
                 fact_type="target_field_name", value="max_pressure_psi", source_agent="Knowledge_Base_Agent",
                 confidence=0.99, timestamp=_past(0), evidence_ref="Target Field Evaluation: max_pressure_psi"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="titan-valve-v10",
                 fact_type="target_field_confidence", value=0.94, source_agent="Knowledge_Base_Agent",
                 confidence=0.96, timestamp=_past(0), evidence_ref="Catalog DB Field 'max_pressure_psi': confidence=0.94, value=3000 PSI"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="titan-valve-v10",
                 fact_type="target_field_status", value="validated", source_agent="Knowledge_Base_Agent",
                 confidence=0.95, timestamp=_past(0), evidence_ref="Validation status: VALIDATED by Engineering Plausibility Rule"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="titan-valve-v10",
                 fact_type="enrichment_method", value="source_data", source_agent="Knowledge_Base_Agent",
                 confidence=0.98, timestamp=_past(0), evidence_ref="Lineage: Extracted directly from manufacturer spec sheet row 14"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="titan-valve-v10",
                 fact_type="field_plausibility_passed", value=True, source_agent="Candidate_Activity_Agent",
                 confidence=0.95, timestamp=_past(0), evidence_ref="Range check passed: 3000 PSI is within standard valve operating limits [500, 10000]"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="titan-valve-v10",
                 fact_type="is_regulated_field", value=True, source_agent="Compliance_Registry_Agent",
                 confidence=0.90, timestamp=_past(0), evidence_ref="High-pressure rating classification rule"),
        ],
    }


def generate_d9_scenario() -> dict[str, Any]:
    """D9: Catalog Expansion Opportunity — qualify fully validated product for cross-channel marketplace expansion."""
    return {
        "decision": DecisionRequest(
            decision_id="DEC-D9-001",
            tenant_id=TENANT_ID,
            decision_type=DecisionType.D9,
            primary_entity_type=EntityType.PRODUCT,
            primary_entity_id="thermocool-tc100",
            requested_by="CAT-OPS-01",
            description="ThermoCool TC-100 Heat Exchanger has 98% completeness and 0.96 confidence. Qualifies for multi-channel marketplace syndication expansion.",
            urgency_score=0.50,
        ),
        "facts": [
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="thermocool-tc100",
                 fact_type="overall_completeness_pct", value=98.0, source_agent="CRM_ATS_Agent",
                 confidence=0.99, timestamp=_past(0), evidence_ref="Catalog DB: 49/50 attributes populated and verified (98%)"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="thermocool-tc100",
                 fact_type="aggregate_confidence", value=0.96, source_agent="Knowledge_Base_Agent",
                 confidence=0.98, timestamp=_past(0), evidence_ref="Aggregate field confidence score across all specs: 0.96"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="thermocool-tc100",
                 fact_type="needs_review_count", value=0, source_agent="CRM_ATS_Agent",
                 confidence=0.99, timestamp=_past(0), evidence_ref="0 fields flagged or in needs_review status"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="thermocool-tc100",
                 fact_type="channel_syndication_fit", value="Exceeds minimum requirements for Amazon B2B, Grainger, Fastenal, and Ferguson", source_agent="Knowledge_Base_Agent",
                 confidence=0.94, timestamp=_past(0), evidence_ref="Channel Schema Mapping Validator"),
            Fact(tenant_id=TENANT_ID, entity_type=EntityType.PRODUCT, entity_id="thermocool-tc100",
                 fact_type="cross_channel_compliance_cleared", value=True, source_agent="Compliance_Registry_Agent",
                 confidence=0.98, timestamp=_past(0), evidence_ref="AHRI Standard 400 & ASME Section VIII compliance certificates active"),
        ],
    }


# ── Historical Outcomes for Learning Loop Warm-Start ─────────────────────────

def generate_historical_outcomes() -> list[dict]:
    """
    Generate 225 realistic historical outcomes in the Catalog Intelligence domain
    for warm-starting the Brier calibration and EMA learning loops (§12, §13).

    Distribution:
      D1 (Listing Readiness Risk):         35
      D2 (Category/Channel Placement):     25
      D3 (Data Decay Risk):                25
      D4 (Re-validation Cycle):            20
      D5 (Incomplete Listing Promotion):   35
      D6 (Source Reliability Health):      20
      D7 (Certification/Compliance Gap):   30
      D8 (Publish-Confidence Threshold):   20
      D9 (Catalog Expansion Opportunity):  15
      ----------------------------------------
      Total Historical Records:           225
    """
    outcomes = []
    now = datetime.utcnow()

    # Per-decision counts summing to 225
    counts = {
        "D1": 35,
        "D2": 25,
        "D3": 25,
        "D4": 20,
        "D5": 35,
        "D6": 20,
        "D7": 30,
        "D8": 20,
        "D9": 15,
    }

    templates = {
        "D1": {
            "accepted": [
                ("listing_published_same_day", True, 0.92),
                ("listing_published_in_2_days", True, 0.88),
                ("listing_published_in_2_days", True, 0.85),
                ("listing_published_in_3_days", True, 0.82),
                ("listing_published_in_3_days", True, 0.80),
                ("listing_published_in_5_days", True, 0.75),
                ("listing_published_same_day", True, 0.90),
                ("launch_delayed_for_data_cleaning", True, 0.65),
            ],
            "overridden": [
                ("unlisted_product_missed_campaign", False, 0.50),
                ("launch_delayed_for_data_cleaning", True, 0.60),
                ("missing_specs_blocked_publish", False, 0.45),
                ("unlisted_product_missed_campaign", False, 0.40),
            ],
            "accept_ratio": 0.77,
        },
        "D2": {
            "accepted": [
                ("optimal_channel_placement_high_conversion", True, 0.88),
                ("top_category_rank_achieved", True, 0.92),
                ("secondary_category_placed", True, 0.70),
                ("channel_syndication_approved", True, 0.85),
                ("taxonomy_mapped_zero_disputes", True, 0.86),
            ],
            "overridden": [
                ("misclassification_corrected_by_curator", False, 0.55),
                ("channel_rejection_for_category_mismatch", False, 0.45),
                ("secondary_category_placed", True, 0.60),
            ],
            "accept_ratio": 0.80,
        },
        "D3": {
            "accepted": [
                ("source_reconciled_with_fresh_spec", True, 0.88),
                ("stale_pricing_corrected_before_sales", True, 0.85),
                ("specs_verified_with_manufacturer", True, 0.82),
                ("automated_reconciliation_cleared", True, 0.90),
                ("source_reconciled_with_fresh_spec", True, 0.86),
            ],
            "overridden": [
                ("outdated_voltage_caused_rma_return", False, 0.48),
                ("decayed_data_flagged_by_buyer", False, 0.52),
                ("stale_pricing_corrected_before_sales", True, 0.68),
                ("outdated_voltage_caused_rma_return", False, 0.40),
            ],
            "accept_ratio": 0.72,
        },
        "D4": {
            "accepted": [
                ("revalidation_audit_passed", True, 0.88),
                ("annual_ul_audit_renewed", True, 0.94),
                ("minor_spec_drift_corrected", True, 0.80),
                ("missed_spec_revision_caught_early", True, 0.78),
                ("deprecated_spec_archived", True, 0.82),
            ],
            "overridden": [
                ("unnoticed_spec_drift_caused_support_ticket", False, 0.50),
                ("audit_deferred_by_operator", False, 0.55),
                ("minor_spec_drift_corrected", True, 0.65),
            ],
            "accept_ratio": 0.80,
        },
        "D5": {
            "accepted": [
                ("3_tier_enrichment_unlocked_listing", True, 0.90),
                ("incomplete_listing_enriched_to_95pct", True, 0.85),
                ("enrichment_yielded_high_demand_sales", True, 0.88),
                ("3_tier_enrichment_unlocked_listing", True, 0.92),
                ("incomplete_listing_enriched_to_95pct", True, 0.82),
            ],
            "overridden": [
                ("context_insufficient_manual_entry", False, 0.45),
                ("unverified_inferred_field_rejected", False, 0.40),
                ("incomplete_listing_enriched_to_95pct", True, 0.65),
            ],
            "accept_ratio": 0.80,
        },
        "D6": {
            "accepted": [
                ("supplier_feed_repaired_after_audit", True, 0.80),
                ("failing_batch_quarantined_safely", True, 0.86),
                ("vendor_re_mapped_csv_headers", True, 0.76),
                ("supplier_feed_syntax_rate_recovered", True, 0.82),
            ],
            "overridden": [
                ("unquarantined_bad_batch_polluted_catalog", False, 0.35),
                ("vendor_dispute_over_schema_rules", False, 0.48),
                ("vendor_re_mapped_csv_headers", True, 0.65),
            ],
            "accept_ratio": 0.75,
        },
        "D7": {
            "accepted": [
                ("compliance_veto_prevented_delisting", True, 0.96),
                ("iso_cert_verified_on_time", True, 0.92),
                ("unverified_marketing_claim_blocked", True, 0.95),
                ("listing_delayed_for_lab_cert", True, 0.85),
                ("compliance_veto_prevented_delisting", True, 0.94),
                ("iso_cert_verified_on_time", True, 0.90),
            ],
            "overridden": [
                ("regulatory_fine_for_uncertified_sale", False, 0.30),
                ("marketplace_delisting_penalty", False, 0.32),
                ("listing_delayed_for_lab_cert", True, 0.60),
                ("regulatory_fine_for_uncertified_sale", False, 0.25),
            ],
            "accept_ratio": 0.80,
        },
        "D8": {
            "accepted": [
                ("field_published_with_zero_disputes", True, 0.90),
                ("auto_publish_threshold_cleared", True, 0.88),
                ("low_confidence_field_flagged_for_human", True, 0.80),
                ("dimensional_spec_validated", True, 0.84),
            ],
            "overridden": [
                ("low_confidence_field_published_in_error", False, 0.40),
                ("human_corrected_voltage_threshold", True, 0.65),
                ("field_published_with_zero_disputes", True, 0.75),
            ],
            "accept_ratio": 0.80,
        },
        "D9": {
            "accepted": [
                ("syndicated_to_3_marketplaces_2x_gmv", True, 0.92),
                ("cross_listing_approved_b2b_portal", True, 0.88),
                ("partner_schema_accepted_cleanly", True, 0.90),
            ],
            "overridden": [
                ("expansion_delayed_for_region_rules", False, 0.45),
                ("cross_listing_approved_b2b_portal", True, 0.65),
                ("partner_schema_accepted_cleanly", True, 0.70),
            ],
            "accept_ratio": 0.80,
        },
    }

    for dt, total_n in counts.items():
        cfg = templates[dt]
        acc_list = cfg["accepted"]
        ovr_list = cfg["overridden"]
        acc_count = int(total_n * cfg["accept_ratio"])

        for i in range(total_n):
            days_ago = random.randint(5, 180)
            if i < acc_count:
                t = acc_list[i % len(acc_list)]
                human_dec = HumanDecision.ACCEPT
            else:
                t = ovr_list[(i - acc_count) % len(ovr_list)]
                human_dec = HumanDecision.EDIT if (i % 2 == 0) else HumanDecision.REJECT

            outcomes.append({
                "decision_type": dt,
                "outcome": Outcome(
                    decision_id=f"HIST-{dt}-{i+1:03d}",
                    action_id=f"ACT-{dt}-{i+1:03d}",
                    human_decision=human_dec,
                    downstream_result=t[0],
                    predicted_confidence=max(0.2, min(0.99, t[2] + random.uniform(-0.03, 0.03))),
                    was_correct=t[1],
                    recorded_at=now - timedelta(days=days_ago),
                    resolved_at=now - timedelta(days=max(0, days_ago - random.randint(1, 14))),
                ),
                "summary": f"{dt} decision: {t[0]} (confidence: {t[2]:.2f}, correct: {t[1]})",
            })

    return outcomes


def get_all_scenarios() -> dict[str, dict]:
    """Return all pre-built decision scenarios indexed by decision type."""
    return {
        "D1": generate_d1_scenario(),
        "D2": generate_d2_scenario(),
        "D3": generate_d3_scenario(),
        "D4": generate_d4_scenario(),
        "D5": generate_d5_scenario(),
        "D6": generate_d6_scenario(),
        "D7": generate_d7_scenario(),
        "D8": generate_d8_scenario(),
        "D9": generate_d9_scenario(),
    }
