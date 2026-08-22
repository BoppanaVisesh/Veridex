"""
Veridex NBA Platform — Configuration (§3.4, §3.6, §3.7, §3.10)

All tunable parameters in one place:
- Decision-type checklists (required evidence per D1-D9 with weights)
- Bidding base priority weights (hot-reloadable)
- VoI parameters, DRE confidence thresholds
- Influence budget constants
- Null-action threshold
- Model routing (Flash vs Pro)

Design decision: Gemini is the LLM provider (free-tier friendly for hackathon).
Embedding uses local sentence-transformers (all-MiniLM-L6-v2) to avoid extra API dependency
and keep the embedding space consistent across Precedent Agent and Planner capability matching.
"""

from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM Configuration ─────────────────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Cost-aware model routing (§7):
# - Compliance and rule-based nodes: no LLM call at all
# - Deterministic/structured bidders (Ops, Finance): cheaper/faster model
# - Planner, Explanation, ambiguous bidders (Risk, CS): stronger model
MODEL_PRO = "gemini-2.0-flash"       # "stronger" model for ambiguous reasoning
MODEL_FLASH = "gemini-2.0-flash"     # cheaper model for structured tasks
# In production, MODEL_PRO would be gemini-1.5-pro or similar.
# For hackathon, both use flash to keep costs zero.

# Embedding model — local, no API dependency.
# Same model for both Precedent Agent vector search and Planner capability matching
# so the embedding space is consistent across both features.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# ── Decision-Type Checklists (§3.4) ──────────────────────────────────────────
# Each decision type has a list of required evidence fact-types with weights.
# Weight = how much this evidence matters for this decision type.
# The DRE uses these to compute VoI scores: weight × (1 − current_confidence).

DECISION_CHECKLISTS: dict[str, list[dict]] = {
    "D1": [  # Listing Readiness Risk — Product aging without complete/validated data before publish deadline
        {"fact_type": "product_status",                 "weight": 1.00, "compliance": False},
        {"fact_type": "product_missing_flagged_count",  "weight": 0.95, "compliance": False},
        {"fact_type": "field_completeness_pct",         "weight": 0.90, "compliance": False},
        {"fact_type": "product_age_days",               "weight": 0.85, "compliance": False},
        {"fact_type": "certification_status",           "weight": 0.80, "compliance": True},
        {"fact_type": "price_confidence",               "weight": 0.70, "compliance": False},
        {"fact_type": "specs_validation_status",        "weight": 0.75, "compliance": False},
    ],
    "D2": [  # Category/Channel Placement — Best catalog category/channel for a product
        {"fact_type": "category_value",                 "weight": 1.00, "compliance": False},
        {"fact_type": "category_confidence",            "weight": 0.95, "compliance": False},
        {"fact_type": "comparable_products_count",      "weight": 0.85, "compliance": False},
        {"fact_type": "taxonomy_completeness",          "weight": 0.80, "compliance": False},
        {"fact_type": "material_spec",                  "weight": 0.75, "compliance": False},
        {"fact_type": "channel_compliance_rules",       "weight": 0.70, "compliance": True},
    ],
    "D3": [  # Data Decay Risk — Product data going stale or contradicted by newer source updates
        {"fact_type": "newest_evidence_age_days",       "weight": 1.00, "compliance": False},
        {"fact_type": "conflicted_fields_count",        "weight": 0.95, "compliance": False},
        {"fact_type": "days_since_validation",          "weight": 0.90, "compliance": False},
        {"fact_type": "source_evidence_spread",         "weight": 0.75, "compliance": False},
        {"fact_type": "pricing_freshness",              "weight": 0.80, "compliance": False},
        {"fact_type": "certification_expiry",           "weight": 0.85, "compliance": True},
    ],
    "D4": [  # Re-validation Cycle — Product data due for periodic re-verification
        {"fact_type": "days_since_last_cycle",          "weight": 1.00, "compliance": False},
        {"fact_type": "field_confidence_distribution",  "weight": 0.90, "compliance": False},
        {"fact_type": "flagged_fields_count",           "weight": 0.85, "compliance": False},
        {"fact_type": "supplier_catalog_update",        "weight": 0.75, "compliance": False},
        {"fact_type": "regulatory_audit_schedule",      "weight": 0.80, "compliance": True},
    ],
    "D5": [  # Incomplete Listing Promotion — Low-completeness product needs prioritized enrichment
        {"fact_type": "field_completeness_pct",         "weight": 1.00, "compliance": False},
        {"fact_type": "missing_fields_count",           "weight": 0.95, "compliance": False},
        {"fact_type": "enrichment_success_ratio",       "weight": 0.85, "compliance": False},
        {"fact_type": "context_text_availability",      "weight": 0.80, "compliance": False},
        {"fact_type": "mandatory_attributes_status",    "weight": 0.90, "compliance": True},
    ],
    "D6": [  # Source Reliability Health — Data source/supplier batch showing declining validation ratio
        {"fact_type": "source_label",                   "weight": 1.00, "compliance": False},
        {"fact_type": "source_validation_ratio",        "weight": 0.95, "compliance": False},
        {"fact_type": "source_historical_trend",        "weight": 0.85, "compliance": False},
        {"fact_type": "syntax_failure_rate",            "weight": 0.80, "compliance": False},
        {"fact_type": "source_compliance_violations",   "weight": 0.90, "compliance": True},
    ],
    "D7": [  # Certification/Compliance Gap — Product missing required certification or unverifiable compliance
        {"fact_type": "certification_value",            "weight": 1.00, "compliance": True},
        {"fact_type": "certification_status",           "weight": 1.00, "compliance": True},
        {"fact_type": "certification_confidence",       "weight": 0.95, "compliance": True},
        {"fact_type": "is_compliance_blocked",          "weight": 1.00, "compliance": True},
        {"fact_type": "safety_standards_mapping",       "weight": 0.85, "compliance": True},
        {"fact_type": "supplier_accreditation_proof",   "weight": 0.90, "compliance": True},
    ],
    "D8": [  # Publish-Confidence Threshold — Specific field confidence high enough to publish as-is
        {"fact_type": "target_field_name",              "weight": 1.00, "compliance": False},
        {"fact_type": "target_field_confidence",        "weight": 0.95, "compliance": False},
        {"fact_type": "target_field_status",            "weight": 0.90, "compliance": False},
        {"fact_type": "enrichment_method",              "weight": 0.85, "compliance": False},
        {"fact_type": "field_plausibility_passed",      "weight": 0.80, "compliance": False},
        {"fact_type": "is_regulated_field",             "weight": 0.85, "compliance": True},
    ],
    "D9": [  # Catalog Expansion Opportunity — Product verified/enriched well enough for cross-listing expansion
        {"fact_type": "overall_completeness_pct",       "weight": 1.00, "compliance": False},
        {"fact_type": "aggregate_confidence",           "weight": 0.95, "compliance": False},
        {"fact_type": "needs_review_count",             "weight": 0.90, "compliance": False},
        {"fact_type": "channel_syndication_fit",        "weight": 0.80, "compliance": False},
        {"fact_type": "cross_channel_compliance_cleared","weight": 0.85, "compliance": True},
    ],
}


# ── Bidding Configuration (§3.6) ─────────────────────────────────────────────

# Base priority weights per bidder — hot-reloadable so judges can see tuning live.
# These are the starting weights; the learning service adjusts them from outcomes.
BASE_BIDDING_WEIGHTS: dict[str, float] = {
    "Revenue":         0.25,
    "Risk":            0.20,
    "CustomerSuccess": 0.15,
    "Finance":         0.15,
    "Compliance":      0.15,  # Note: Compliance veto bypasses weighting entirely
    "Ops":             0.10,
}

# Null-action threshold (§3.7): if no action's aggregate weighted score clears this,
# the Optimizer outputs "null_no_action" with full rationale.
NULL_ACTION_THRESHOLD = 0.38

# ── DRE Configuration (§3.4) ─────────────────────────────────────────────────

# Minimum per-fact confidence for DRE to consider it "covered"
DRE_CONFIDENCE_THRESHOLD = 0.5

# Minimum overall readiness score (weighted avg of fact confidences) for "Ready"
DRE_READINESS_THRESHOLD = 0.65

# "Ready-with-caveats" range: above this but below READINESS, proceed but flag
DRE_CAVEATS_THRESHOLD = 0.45

# Maximum DRE/VoI loop iterations (budget counter)
MAX_DRE_ITERATIONS = 3

# ── Influence Budget Configuration (§3.6.1) ──────────────────────────────────
# The real auction mechanic — built as additive layer over core pipeline.

INFLUENCE_WIN_COST = 0.08        # Winning costs influence, immediately
INFLUENCE_REFUND_GOOD = 0.05     # Correct call partially refunds
INFLUENCE_PENALTY_BAD = 0.05     # Wrong call costs more (no refund)
INFLUENCE_REPLENISH_RATE = 0.01  # Slow, unconditional replenishment per resolved decision

# ── Learning Service Configuration (§3.10) ───────────────────────────────────

# Minimum sample count before EMA weight updates move at all
MIN_SAMPLE_SIZE_FOR_UPDATE = 1

# Minimum sample count before Brier scores are reported
MIN_SAMPLE_SIZE_FOR_CALIBRATION = 1

# EMA learning rate (dampened to avoid noise)
EMA_LEARNING_RATE = 0.05

# ── Agent Capability Schemas ─────────────────────────────────────────────────
# Each agent declares what fact-types it can produce.
# The Planner uses cosine similarity (≥ 0.8) to route evidence gaps to agents.

AGENT_CAPABILITIES: dict[str, list[str]] = {
    "Catalog_Evidence_Agent": [
        "product_status", "product_missing_flagged_count", "field_completeness_pct",
        "product_age_days", "certification_status", "price_confidence", "specs_validation_status",
        "category_value", "category_confidence", "comparable_products_count",
        "taxonomy_completeness", "material_spec", "channel_compliance_rules",
        "newest_evidence_age_days", "conflicted_fields_count", "days_since_validation",
        "source_evidence_spread", "pricing_freshness", "certification_expiry",
        "days_since_last_cycle", "field_confidence_distribution", "flagged_fields_count",
        "supplier_catalog_update", "regulatory_audit_schedule",
        "missing_fields_count", "enrichment_success_ratio", "context_text_availability",
        "mandatory_attributes_status", "source_label", "source_validation_ratio",
        "source_historical_trend", "syntax_failure_rate", "source_compliance_violations",
        "certification_value", "certification_confidence", "is_compliance_blocked",
        "safety_standards_mapping", "supplier_accreditation_proof",
        "target_field_name", "target_field_confidence", "target_field_status",
        "enrichment_method", "field_plausibility_passed", "is_regulated_field",
        "overall_completeness_pct", "aggregate_confidence", "needs_review_count",
        "channel_syndication_fit", "cross_channel_compliance_cleared",
    ],
    "CRM_ATS_Agent": [
        "product_status", "product_missing_flagged_count", "field_completeness_pct",
        "product_age_days", "missing_fields_count", "overall_completeness_pct",
        "needs_review_count", "context_text_availability",
        # Legacy support
        "job_order_details", "pipeline_status", "account_history", "contract_details",
    ],
    "Email_Agent": [
        "supplier_communication_signal", "supplier_catalog_update",
        "buyer_feedback_sentiment", "pricing_freshness",
        # Legacy support
        "email_sentiment", "candidate_response_pattern", "competing_offer_signal",
    ],
    "Meetings_Agent": [
        "vendor_review_notes", "qbr_sentiment", "channel_partner_feedback",
        # Legacy support
        "interview_feedback", "client_satisfaction_signal",
    ],
    "Candidate_Activity_Agent": [
        "specs_validation_status", "flagged_fields_count", "conflicted_fields_count",
        "days_since_validation", "days_since_last_cycle", "field_confidence_distribution",
        "field_plausibility_passed",
        # Legacy support
        "timesheet_pattern", "portal_activity", "assessment_score",
    ],
    "Knowledge_Base_Agent": [
        "category_value", "category_confidence", "taxonomy_completeness",
        "material_spec", "channel_syndication_fit", "enrichment_method",
        "enrichment_success_ratio", "target_field_name", "target_field_confidence",
        "target_field_status", "aggregate_confidence",
        # Legacy support
        "sourcing_playbook", "compliance_rules", "rate_card_policy",
    ],
    "Market_Data_Agent": [
        "comparable_products_count", "price_confidence", "source_evidence_spread",
        "source_label", "source_validation_ratio", "source_historical_trend",
        "syntax_failure_rate", "newest_evidence_age_days",
        # Legacy support
        "market_bill_rate", "talent_supply_demand", "market_demand", "margin_analysis",
    ],
    "Compliance_Registry_Agent": [
        "certification_value", "certification_status", "certification_confidence",
        "is_compliance_blocked", "safety_standards_mapping", "supplier_accreditation_proof",
        "channel_compliance_rules", "certification_expiry", "regulatory_audit_schedule",
        "mandatory_attributes_status", "source_compliance_violations", "is_regulated_field",
        "cross_channel_compliance_cleared",
        # Legacy support
        "work_auth_status", "background_check_status", "expiry_timeline",
    ],
}

# ── Action Templates (§3.7) ──────────────────────────────────────────────────
# Typed action templates with named slots per decision type.

ACTION_TEMPLATES: dict[str, dict] = {
    "D1": {
        "template_name": "ListingReadinessAction",
        "slots": ["enrichment_target_slot", "priority_tier_slot", "reviewer_slot"],
        "description_template": "Accelerate validation and enrichment for {product_id}. Focus on {enrichment_target_slot} before publish deadline.",
    },
    "D2": {
        "template_name": "CategoryPlacementAction",
        "slots": ["target_category_slot", "channel_slot", "mapping_rule_slot"],
        "description_template": "Assign {product_id} to category '{target_category_slot}' for channel {channel_slot} based on {mapping_rule_slot}.",
    },
    "D3": {
        "template_name": "DataDecayAction",
        "slots": ["refresh_action_slot", "source_reconciliation_slot"],
        "description_template": "Reconcile conflicting source evidence for {product_id}. Trigger {refresh_action_slot} with supplier feed.",
    },
    "D4": {
        "template_name": "RevalidationAction",
        "slots": ["audit_action_slot", "schedule_window_slot"],
        "description_template": "Perform periodic re-validation audit on {product_id} within {schedule_window_slot}. {audit_action_slot}.",
    },
    "D5": {
        "template_name": "ListingPromotionAction",
        "slots": ["enrichment_pipeline_slot", "target_attributes_slot"],
        "description_template": "Run prioritized 3-tier enrichment on {product_id} for {target_attributes_slot} via {enrichment_pipeline_slot}.",
    },
    "D6": {
        "template_name": "SourceHealthAction",
        "slots": ["supplier_feed_slot", "quarantine_action_slot"],
        "description_template": "Inspect data quality for source {supplier_feed_slot}. Apply {quarantine_action_slot} on failing batches.",
    },
    "D7": {
        "template_name": "ComplianceGapAction",
        "slots": ["remediation_action_slot", "compliance_officer_slot"],
        "description_template": "Block product publication for {product_id} due to unverified compliance. {remediation_action_slot} assigned to {compliance_officer_slot}.",
    },
    "D8": {
        "template_name": "PublishConfidenceAction",
        "slots": ["field_target_slot", "approval_threshold_slot"],
        "description_template": "Evaluate publication gate for {field_target_slot} of {product_id}. Requires {approval_threshold_slot}.",
    },
    "D9": {
        "template_name": "CatalogExpansionAction",
        "slots": ["target_marketplace_slot", "syndication_tier_slot"],
        "description_template": "Approve {product_id} for cross-channel catalog syndication on {target_marketplace_slot} ({syndication_tier_slot}).",
    },
}

# ── Model Routing (§7) ───────────────────────────────────────────────────────
# Which pipeline nodes use which model tier.

MODEL_ROUTING: dict[str, str] = {
    # No LLM at all (deterministic)
    "Compliance_Registry_Agent": "none",
    "Compliance_Bidder":         "none",
    "Optimizer":                 "none",

    # Flash (cheaper, narrow/structured)
    "Finance_Bidder":            MODEL_FLASH,
    "Ops_Bidder":                MODEL_FLASH,
    "Contradiction_Detector":    MODEL_FLASH,
    "Missing_Info_Detector":     MODEL_FLASH,

    # Pro (stronger, ambiguous reasoning)
    "Planner_Agent":             MODEL_PRO,
    "Revenue_Bidder":            MODEL_PRO,
    "Risk_Bidder":               MODEL_PRO,
    "CustomerSuccess_Bidder":    MODEL_PRO,
    "Explanation_Engine":        MODEL_PRO,

    # Evidence agents (use Flash for extraction, data is structured input)
    "CRM_ATS_Agent":             MODEL_FLASH,
    "Email_Agent":               MODEL_FLASH,
    "Meetings_Agent":            MODEL_FLASH,
    "Candidate_Activity_Agent":  MODEL_FLASH,
    "Knowledge_Base_Agent":      MODEL_FLASH,
    "Market_Data_Agent":         MODEL_FLASH,
}
