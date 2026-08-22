"""
Veridex NBA Platform — Multi-Objective Bidding Layer (§3.6)

6 bidder agents scoring candidate actions for Catalog Intelligence decisions (D1–D9).
Each bid is a (score, rationale, confidence, evidence_refs) tuple.

Score is normalized to a common 0-1 scale: expected positive impact on the decision objective.

Compliance bidder is ALWAYS deterministic (no LLM, §3.6) with hard veto authority.
Other bidders use structured product-domain reasoning.

Confidence propagation rule (§3.6):
    bidder_confidence = min(own_reasoning_confidence, min(cited_evidence_confidences))
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.models import (
    Bid, BidderType, Fact, DecisionType,
    compute_bidder_confidence,
)


class BaseBidder(ABC):
    """Base class for all bidder agents."""
    bidder_type: BidderType
    uses_llm: bool = True

    @abstractmethod
    def bid(
        self,
        decision_id: str,
        decision_type: str,
        facts: list[Fact],
        candidate_actions: list[dict] | None = None,
    ) -> list[Bid]:
        """Generate bids for the given decision context."""
        ...

    def _compute_confidence(
        self,
        own_confidence: float,
        evidence_refs: list[str],
        facts: list[Fact],
    ) -> float:
        """Apply confidence propagation rule (§3.6)."""
        cited_confidences = []
        for ref in evidence_refs:
            for f in facts:
                if f.evidence_ref == ref:
                    cited_confidences.append(f.confidence)
                    break
        return compute_bidder_confidence(own_confidence, cited_confidences)

    def _get_facts_of_type(self, facts: list[Fact], fact_type: str) -> list[Fact]:
        return [f for f in facts if f.fact_type == fact_type]


class RevenueBidder(BaseBidder):
    """Revenue Agent — Evaluates catalog commercial impact, sales velocity, and gross margin."""
    bidder_type = BidderType.Revenue

    def bid(self, decision_id, decision_type, facts, candidate_actions=None):
        bids = []
        relevant_facts = (
            self._get_facts_of_type(facts, "field_completeness_pct")
            + self._get_facts_of_type(facts, "price_confidence")
            + self._get_facts_of_type(facts, "category_value")
            + self._get_facts_of_type(facts, "overall_completeness_pct")
            + self._get_facts_of_type(facts, "pricing_freshness")
            + self._get_facts_of_type(facts, "product_age_days")
        )
        evidence_refs = [f.evidence_ref for f in relevant_facts[:5]]

        if decision_type == "D1":  # Listing Readiness Risk
            score = 0.82
            rationale = "High revenue velocity risk: unlisted inventory incurs daily opportunity cost. Publishing complete, validated product specs unlocks immediate channel search visibility and buyer checkout."
        elif decision_type == "D2":  # Category/Channel Placement
            score = 0.78
            rationale = "Target category exhibits high buyer search volume and strong historical conversion rates. Proper placement maximizes catalog traffic and prevents misdirected buyer bounces."
        elif decision_type == "D3":  # Data Decay Risk
            score = 0.68
            rationale = "Stale pricing or deprecated specifications directly risk abandoned carts and margin loss. Reconciling with fresh source data protects conversion rate."
        elif decision_type == "D4":  # Re-validation Cycle
            score = 0.75
            rationale = "Re-validating top-performing catalog items preserves buyer trust, search ranking privileges, and verified merchant badges."
        elif decision_type == "D5":  # Incomplete Listing Promotion
            score = 0.84
            rationale = "High commercial upside: prioritizing 3-tier enrichment on high-demand incomplete listings unlocks new catalog revenue with minimal marginal cost."
        elif decision_type == "D6":  # Source Reliability Health
            score = 0.62
            rationale = "Supplier catalog reliability directly impacts listing throughput and catalog growth speed. Sanitizing vendor data streams protects sales continuity."
        elif decision_type == "D7":  # Certification/Compliance Gap
            score = 0.40
            rationale = "Listing suspension during compliance review creates temporary revenue drag; however, selling uncertified equipment risks catastrophic platform delisting."
        elif decision_type == "D8":  # Publish-Confidence Threshold
            score = 0.72
            rationale = "Commercial attributes meet confidence threshold for live publishing without risking pricing disputes or unfulfilled customer expectations."
        elif decision_type == "D9":  # Catalog Expansion Opportunity
            score = 0.88
            rationale = "Strong revenue expansion opportunity: fully validated product qualifies for multi-channel syndication across partner marketplaces with 3-5x reach."
        else:
            score = 0.55
            rationale = f"Moderate revenue consideration for {decision_type} product decision."

        confidence = self._compute_confidence(0.82, evidence_refs, facts)
        bids.append(Bid(
            decision_id=decision_id,
            bidder=self.bidder_type,
            score=score,
            rationale=rationale,
            confidence=confidence,
            evidence_refs=evidence_refs,
        ))
        return bids


class RiskBidder(BaseBidder):
    """Risk Agent — Product hallucination, spec inaccuracy, and marketplace compliance liability."""
    bidder_type = BidderType.Risk

    def bid(self, decision_id, decision_type, facts, candidate_actions=None):
        risk_facts = (
            self._get_facts_of_type(facts, "conflicted_fields_count")
            + self._get_facts_of_type(facts, "product_missing_flagged_count")
            + self._get_facts_of_type(facts, "flagged_fields_count")
            + self._get_facts_of_type(facts, "syntax_failure_rate")
            + self._get_facts_of_type(facts, "is_compliance_blocked")
        )
        evidence_refs = [f.evidence_ref for f in risk_facts[:5]]

        has_conflicts = any("conflict" in str(f.value).lower() or (isinstance(f.value, (int, float)) and f.value > 0) for f in self._get_facts_of_type(facts, "conflicted_fields_count"))
        has_flags = any("flag" in str(f.value).lower() or (isinstance(f.value, (int, float)) and f.value > 0) for f in self._get_facts_of_type(facts, "product_missing_flagged_count"))

        if decision_type == "D1":
            score = 0.74
            rationale = "Publishing unvalidated or flagged technical specifications risks incorrect buyer installation, product returns, and channel penalties."
        elif decision_type == "D2":
            score = 0.65
            rationale = "Misclassification risk: assigning an item to an incorrect taxonomy branch causes buyer confusion and potential regulatory misclassification fines."
        elif decision_type == "D3":
            if has_conflicts:
                score = 0.88
                rationale = "HIGH DATA DECAY RISK: Multiple evidence sources provide conflicting raw specifications (e.g. dimensions/voltages). High risk of shipping incorrect product variant."
            else:
                score = 0.60
                rationale = "Moderate data decay risk: source evidence is aging but no active contradictions detected between vendor feeds."
        elif decision_type == "D4":
            score = 0.58
            rationale = "Periodic audit risk: unverified physical attributes accumulating over time increase catalog error drift."
        elif decision_type == "D5":
            score = 0.70
            rationale = "Enrichment risk: ensure 3-tier pipeline does not fabricate specifications (e.g. certifications) without authentic context."
        elif decision_type == "D6":
            score = 0.82
            rationale = "HIGH SOURCE RELIABILITY RISK: Supplier feed exhibits elevated syntax failure and flagging rates. Quarantine and feed re-mapping recommended."
        elif decision_type == "D7":
            score = 0.92
            rationale = "CRITICAL COMPLIANCE RISK: Missing or unverified certification for industrial item creates severe regulatory exposure and safety hazard."
        elif decision_type == "D8":
            score = 0.64
            rationale = "Field confidence evaluation: verify physical dimensions and voltage ratings before committing to syndication payload."
        elif decision_type == "D9":
            score = 0.45
            rationale = "Low risk scenario: product profile is stable and meets cross-channel attribute consistency standards."
        else:
            score = 0.50
            rationale = f"Moderate risk assessment for {decision_type} product decision."

        confidence = self._compute_confidence(0.80, evidence_refs, facts)
        return [Bid(
            decision_id=decision_id,
            bidder=self.bidder_type,
            score=score,
            rationale=rationale,
            confidence=confidence,
            evidence_refs=evidence_refs,
        )]


class CustomerSuccessBidder(BaseBidder):
    """Customer-Success Agent — Buyer experience, technical specification clarity, and return mitigation."""
    bidder_type = BidderType.CustomerSuccess

    def bid(self, decision_id, decision_type, facts, candidate_actions=None):
        cs_facts = (
            self._get_facts_of_type(facts, "field_completeness_pct")
            + self._get_facts_of_type(facts, "taxonomy_completeness")
            + self._get_facts_of_type(facts, "overall_completeness_pct")
            + self._get_facts_of_type(facts, "buyer_feedback_sentiment")
        )
        evidence_refs = [f.evidence_ref for f in cs_facts[:5]]

        if decision_type == "D1":
            score = 0.72
            rationale = "Clear, complete product specifications prevent post-purchase buyer frustration, installation errors, and preventable RMA returns."
        elif decision_type == "D2":
            score = 0.82
            rationale = "Accurate categorization and rich filtering attributes ensure buyers find exact matching parts in catalog search effortlessly."
        elif decision_type == "D3":
            score = 0.76
            rationale = "Reconciling outdated specs protects catalog credibility and ensures buyer documentation accurately matches delivered hardware."
        elif decision_type == "D4":
            score = 0.70
            rationale = "Periodic verification guarantees technical user manuals, spec sheets, and voltage tolerances remain 100% accurate."
        elif decision_type == "D5":
            score = 0.78
            rationale = "Enriching missing attributes (material, dimensions, units) significantly enhances buyer search confidence and catalog clarity."
        elif decision_type == "D6":
            score = 0.65
            rationale = "Maintaining clean supplier ingest feeds prevents gibberish text and placeholder values from degrading the public storefront."
        elif decision_type == "D7":
            score = 0.85
            rationale = "Ensuring accredited safety certifications (ISO/CE/UL) protects end users and upholds high merchant reputation."
        elif decision_type == "D8":
            score = 0.74
            rationale = "High-confidence attribute values reduce buyer support tickets and technical pre-sales inquiry volume."
        elif decision_type == "D9":
            score = 0.80
            rationale = "Rich, complete catalog attributes deliver a superior buyer experience across all syndicated marketplace partner channels."
        else:
            score = 0.60
            rationale = f"Standard customer success evaluation for {decision_type}."

        confidence = self._compute_confidence(0.78, evidence_refs, facts)
        return [Bid(
            decision_id=decision_id,
            bidder=self.bidder_type,
            score=score,
            rationale=rationale,
            confidence=confidence,
            evidence_refs=evidence_refs,
        )]


class FinanceBidder(BaseBidder):
    """Finance Agent — Inventory carrying costs, syndication margins, and cleaning labor expenses."""
    bidder_type = BidderType.Finance

    def bid(self, decision_id, decision_type, facts, candidate_actions=None):
        fin_facts = (
            self._get_facts_of_type(facts, "price_confidence")
            + self._get_facts_of_type(facts, "pricing_freshness")
            + self._get_facts_of_type(facts, "field_completeness_pct")
            + self._get_facts_of_type(facts, "product_age_days")
        )
        evidence_refs = [f.evidence_ref for f in fin_facts[:5]]

        if decision_type == "D1":
            score = 0.68
            rationale = "Unlisted inventory incurs holding cost and ties up working capital. Publishing quickly maximizes gross margin return."
        elif decision_type == "D2":
            score = 0.70
            rationale = "Optimal category assignment aligns product with favorable channel fee schedules and target margin benchmarks."
        elif decision_type == "D3":
            score = 0.72
            rationale = "Outdated pricing directly risks margin erosion or pricing disputes. Reconciling price data protects target profit margins."
        elif decision_type == "D4":
            score = 0.65
            rationale = "Automated re-validation audits prevent expensive manual data hygiene interventions down the line."
        elif decision_type == "D5":
            score = 0.75
            rationale = "Automated 3-tier enrichment costs fractions of a cent per field compared to $5-10 manual data entry labor costs."
        elif decision_type == "D6":
            score = 0.68
            rationale = "Repairing malformed vendor feeds wastes developer and ops hours; supplier feed quality enforcement saves operational budget."
        elif decision_type == "D7":
            score = 0.60
            rationale = "Non-compliant product distribution risks regulatory fines, recall expenses, and warranty liabilities far exceeding listing revenue."
        elif decision_type == "D8":
            score = 0.70
            rationale = "Verifying physical dimensions and weights prevents costly shipping undercharges and dimensional weight logistics penalties."
        elif decision_type == "D9":
            score = 0.82
            rationale = "Multi-channel syndication generates incremental distribution revenue with zero additional product development cost."
        else:
            score = 0.55
            rationale = f"Standard financial assessment for {decision_type}."

        confidence = self._compute_confidence(0.82, evidence_refs, facts)
        return [Bid(
            decision_id=decision_id,
            bidder=self.bidder_type,
            score=score,
            rationale=rationale,
            confidence=confidence,
            evidence_refs=evidence_refs,
        )]


class ComplianceBidder(BaseBidder):
    """
    Compliance Agent — DETERMINISTIC rule evaluation, NEVER an LLM call (§3.6).

    Hard veto power:
    - Missing or unverified certification on regulated items -> VETO.
    - is_compliance_blocked == True -> VETO.
    - certification_status in ("missing", "needs_review") for D7 -> VETO.

    Exempt from influence mechanic. Veto is NEVER outbid.
    """
    bidder_type = BidderType.Compliance
    uses_llm = False  # DETERMINISTIC

    def bid(self, decision_id, decision_type, facts, candidate_actions=None):
        compliance_facts = (
            self._get_facts_of_type(facts, "certification_value")
            + self._get_facts_of_type(facts, "certification_status")
            + self._get_facts_of_type(facts, "certification_confidence")
            + self._get_facts_of_type(facts, "is_compliance_blocked")
            + self._get_facts_of_type(facts, "source_compliance_violations")
            + self._get_facts_of_type(facts, "channel_compliance_rules")
            + self._get_facts_of_type(facts, "certification_expiry")
        )
        evidence_refs = [f.evidence_ref for f in compliance_facts]

        vetoes: list[str] = []

        # Check explicit compliance blocked flag
        for f in self._get_facts_of_type(facts, "is_compliance_blocked"):
            if str(f.value).lower() in ("true", "1", "blocked", "yes"):
                vetoes.append(f"Product publication blocked by regulatory compliance rule (source: {f.evidence_ref})")

        # Check certification status for D7 decisions
        cert_status_facts = self._get_facts_of_type(facts, "certification_status")
        cert_val_facts = self._get_facts_of_type(facts, "certification_value")

        for cs in cert_status_facts:
            cs_val = str(cs.value).lower()
            if cs_val in ("missing", "needs_review", "flagged", "conflicted"):
                if decision_type == "D7":
                    vetoes.append(f"Certification status is '{cs.value}' — missing required verified accreditation")

        for cv in cert_val_facts:
            cv_val = str(cv.value).lower()
            if cv_val in ("unknown", "none", "null", ""):
                if decision_type == "D7":
                    vetoes.append("No accredited certification provided; marketing terms cannot satisfy compliance requirements")

        # Check for source compliance violations
        for sv in self._get_facts_of_type(facts, "source_compliance_violations"):
            if isinstance(sv.value, (int, float)) and sv.value > 0:
                vetoes.append(f"Supplier feed has {sv.value} recorded regulatory violations")

        if vetoes:
            return [Bid(
                decision_id=decision_id,
                bidder=self.bidder_type,
                score=0.0,  # Compliance veto
                rationale="COMPLIANCE VETO: " + " | ".join(vetoes),
                confidence=0.99,  # Deterministic — high confidence
                evidence_refs=evidence_refs,
                is_veto=True,
                veto_reason=" | ".join(vetoes),
            )]
        else:
            return [Bid(
                decision_id=decision_id,
                bidder=self.bidder_type,
                score=0.90,  # No compliance issues
                rationale="All regulatory and certification standards verified: valid accredited certification, no compliance blockers.",
                confidence=0.99,
                evidence_refs=evidence_refs,
                is_veto=False,
            )]


class OpsBidder(BaseBidder):
    """Ops Agent — Automated pipeline throughput, enrichment effort, and data syndication feasibility."""
    bidder_type = BidderType.Ops

    def bid(self, decision_id, decision_type, facts, candidate_actions=None):
        ops_facts = (
            self._get_facts_of_type(facts, "product_missing_flagged_count")
            + self._get_facts_of_type(facts, "enrichment_success_ratio")
            + self._get_facts_of_type(facts, "syntax_failure_rate")
        )
        evidence_refs = [f.evidence_ref for f in ops_facts[:3]]

        if decision_type == "D1":
            score = 0.75
            rationale = "Operational workflow is clear: automated validation cleared standard attributes; remaining missing fields routed to 3-tier enrichment."
        elif decision_type == "D2":
            score = 0.72
            rationale = "Taxonomy mapping rules execute cleanly against standardized catalog taxonomy without custom attribute transformations."
        elif decision_type == "D3":
            score = 0.70
            rationale = "Automated delta synchronization can refresh stale attributes without requiring full database re-indexing."
        elif decision_type == "D4":
            score = 0.78
            rationale = "Batch re-validation scheduled during off-peak processing window to maximize pipeline throughput."
        elif decision_type == "D5":
            score = 0.82
            rationale = "High automation feasibility: 3-tier enrichment engine can process incomplete fields in seconds with full audit trail."
        elif decision_type == "D6":
            score = 0.65
            rationale = "Automated quarantine rules isolate failing supplier batches, protecting healthy ingest queues."
        elif decision_type == "D7":
            score = 0.60
            rationale = "Routing unverified certifications to human specialist audit queue with attached source evidence snippet."
        elif decision_type == "D8":
            score = 0.75
            rationale = "Attribute confidence score satisfies automated publishing rule criteria; no manual review required."
        elif decision_type == "D9":
            score = 0.80
            rationale = "Product payload structure is 100% compliant with partner syndication API schemas."
        else:
            score = 0.65
            rationale = f"Standard operational assessment for {decision_type}. No pipeline blockers identified."

        confidence = self._compute_confidence(0.80, evidence_refs, facts)
        return [Bid(
            decision_id=decision_id,
            bidder=self.bidder_type,
            score=score,
            rationale=rationale,
            confidence=confidence,
            evidence_refs=evidence_refs,
        )]


# ── Bidder Registry ────────────────────────────────────────────────────────

ALL_BIDDERS: dict[str, BaseBidder] = {
    "Revenue": RevenueBidder(),
    "Risk": RiskBidder(),
    "CustomerSuccess": CustomerSuccessBidder(),
    "Finance": FinanceBidder(),
    "Compliance": ComplianceBidder(),
    "Ops": OpsBidder(),
}


def run_all_bidders(
    decision_id: str,
    decision_type: str,
    facts: list[Fact],
) -> list[Bid]:
    """Run all bidders in parallel (simulated) and collect bids."""
    all_bids = []
    for name, bidder in ALL_BIDDERS.items():
        bids = bidder.bid(decision_id, decision_type, facts)
        all_bids.extend(bids)
    return all_bids
