"""
Veridex NBA Platform — Data Contracts (§10)

These are the seams between every component in the architecture.
Every Evidence Agent emits Fact, every Bidder emits Bid, the Optimizer emits Action,
and the Memory/Learning Service consumes Outcome to produce CalibrationRecord.

Freeze these before splitting up build work.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────────

class DecisionType(str, Enum):
    """Nine product-intelligence decision types."""
    D1 = "D1"  # Listing Readiness Risk — Product aging without complete/validated data before publish deadline
    D2 = "D2"  # Category/Channel Placement — Best catalog category/channel for a product given validated attributes
    D3 = "D3"  # Data Decay Risk — Product data going stale or contradicted by newer source updates
    D4 = "D4"  # Re-validation Cycle — Product data due for periodic re-verification (refresh/re-certify/deprecate)
    D5 = "D5"  # Incomplete Listing Promotion — Low-completeness product needs prioritized enrichment
    D6 = "D6"  # Source Reliability Health — Data source/supplier batch showing declining validation ratio
    D7 = "D7"  # Certification/Compliance Gap — Product missing required certification or unverifiable compliance
    D8 = "D8"  # Publish-Confidence Threshold — Specific field confidence high enough to publish as-is
    D9 = "D9"  # Catalog Expansion Opportunity — Product verified/enriched well enough for cross-listing expansion


class BidderType(str, Enum):
    Revenue = "Revenue"
    Risk = "Risk"
    CustomerSuccess = "CustomerSuccess"
    Finance = "Finance"
    Compliance = "Compliance"
    Ops = "Ops"


class DREStatus(str, Enum):
    """Decision Readiness Evaluator output states (§3.4)."""
    READY = "Ready"
    NOT_READY = "Not-Ready"
    READY_WITH_CAVEATS = "Ready-with-caveats"
    BLOCKED = "Blocked"  # Compliance gap, no caveat-path → hard exit to human escalation


class HumanDecision(str, Enum):
    ACCEPT = "accept"
    EDIT = "edit"
    REJECT = "reject"


class PIIClass(str, Enum):
    NONE = "none"
    STANDARD = "standard"
    SENSITIVE = "sensitive"  # Compliance certificate, regulatory documentation, supplier cost


class ActionStatus(str, Enum):
    PROPOSED = "proposed"
    HUMAN_APPROVED = "human_approved"
    HUMAN_EDITED = "human_edited"
    HUMAN_REJECTED = "human_rejected"
    EXECUTED = "executed"


class ActionType(str, Enum):
    RECOMMENDED = "recommended"
    NULL_NO_ACTION = "null_no_action"  # §3.7 — explicit "recommend nothing" output


# ── Entity Types ───────────────────────────────────────────────────────────────

class EntityType(str, Enum):
    PRODUCT = "Product"
    FIELD = "ProductField"
    SOURCE = "DataSource"
    CATEGORY = "Category"
    CATALOG = "Catalog"
    # Aliases for compatibility
    CLIENT = "Product"
    JOB_ORDER = "Product"
    CANDIDATE = "ProductField"
    CONTRACT = "DataSource"
    RECRUITER = "Category"



# ── Core Data Contracts ───────────────────────────────────────────────────────

# Human-input confidence cap (§3.9): a verbal recollection from a busy recruiter
# is NOT a verified record — never written at 0.9+ regardless of phrasing.
HUMAN_INPUT_CONFIDENCE_CAP = 0.6


class Fact(BaseModel):
    """
    The atomic unit of evidence in the shared memory graph.
    Every Evidence Agent produces Facts following this exact contract.

    source_agent="human_input" facts are capped at HUMAN_INPUT_CONFIDENCE_CAP (§3.9).
    Human conversational input can NEVER resolve a compliance-relevant gap.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    entity_type: EntityType
    entity_id: str
    fact_type: str  # e.g. "competing_offer_signal", "work_auth_status"
    value: str | float | bool
    source_agent: str  # which Evidence Agent produced it
    confidence: float = Field(ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    evidence_ref: str  # pointer to raw snippet (email line, transcript span, ATS record id)
    pii_class: PIIClass = PIIClass.NONE  # drives §11 access scoping

    def model_post_init(self, __context) -> None:
        """Enforce human-input confidence cap."""
        if self.source_agent == "human_input" and self.confidence > HUMAN_INPUT_CONFIDENCE_CAP:
            object.__setattr__(self, 'confidence', HUMAN_INPUT_CONFIDENCE_CAP)


class EvidenceGap(BaseModel):
    """Output of the DRE's gap analysis — what's missing and how much it matters."""
    decision_id: str
    fact_type: str
    checklist_weight: float  # rule-based VoI weight (§3.4)
    current_confidence: float = 0.0  # 0 if entirely missing
    is_compliance_relevant: bool = False  # triggers hard Not-Ready / Blocked (§3.4)
    voi_score: float = 0.0  # computed: weight × (1 − current_confidence)

    def compute_voi(self) -> float:
        """Value-of-Information: weight × (1 − current_confidence). Highest goes first."""
        self.voi_score = self.checklist_weight * (1.0 - self.current_confidence)
        return self.voi_score


class DecisionRequest(BaseModel):
    """A business decision request entering the platform."""
    tenant_id: str
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    decision_type: DecisionType
    primary_entity_type: EntityType = EntityType.JOB_ORDER
    primary_entity_id: str
    requested_by: str  # recruiter/AM user id
    created_at: datetime = Field(default_factory=datetime.utcnow)
    description: str = ""  # natural language description
    urgency_score: float = 0.5  # for queue triage (§3.9), not FIFO


class TaskPlan(BaseModel):
    """Output of the Planner Agent — decomposed evidence requirements."""
    decision_id: str
    decision_type: DecisionType
    required_fact_types: list[str]
    assigned_agents: list[str]  # agent names that can cover the required facts
    uncovered_fact_types: list[str] = []  # gaps needing Dynamic Agent Creator
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Bid(BaseModel):
    """
    Output of a Bidder Agent (§3.6).

    score is normalized 0.0-1.0: "expected positive impact of this action on this decision."
    NOT a free-floating, bidder-specific magnitude — every bidder converts its own reasoning
    into this shared 0-1 impact scale before bidding.

    confidence is derived per §3.6's propagation rule:
        bidder_confidence = min(own_reasoning_confidence, min(cited_evidence_confidences))
    Not asserted independently.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    decision_id: str
    bidder: BidderType
    proposed_action_id: str = ""
    proposed_action_summary: str = ""
    score: float = Field(ge=0.0, le=1.0)
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: list[str] = []
    is_veto: bool = False  # Compliance only; hard-removes the action regardless of score
    veto_reason: str = ""  # explanation when is_veto=True


class SlotAssignment(BaseModel):
    """A single slot in a composed action template (§3.7)."""
    slot_name: str  # e.g. "primary_candidate_slot", "backup_candidate_slot"
    filled_by: str  # entity id (candidate id, etc.)
    source_bid_id: str  # which bid proposed filling this slot — traceability for "why not X"
    score: float = 0.0


class SimilarPastDecision(BaseModel):
    """
    Output of the Precedent Agent (§3.2).
    Retrieved by vector search over past Outcome+Fact bundles filtered by decision_type.
    Surfaced by the Explanation Engine (§3.8) as precedent context.

    Only emitted when similarity_score clears the no-match floor —
    no instances exist for a query with no good match.
    """
    decision_id: str
    decision_type: DecisionType
    similarity_score: float
    action_taken_summary: str
    outcome_summary: str  # e.g. "retained after same-day call"


class Action(BaseModel):
    """
    Output of the Multi-Objective Optimizer (§3.7).

    action_type can be "null_no_action" when no candidate action's aggregate score
    clears the configurable threshold — an explicit, explained "recommend nothing."
    """
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    decision_id: str
    description: str
    action_type: ActionType = ActionType.RECOMMENDED
    composed_from: list[str] = []  # bid IDs this was synthesized from
    aggregate_score: float = 0.0
    status: ActionStatus = ActionStatus.PROPOSED
    slots: list[SlotAssignment] = []
    explanation: str = ""
    counterfactuals: list[str] = []
    similar_past_cases: list[SimilarPastDecision] = []
    losing_bids_summary: list[dict] = []  # [{bidder, rationale, score}]
    contradictions: list[str] = []
    missing_info: list[str] = []


class FulfillmentAction(Action):
    """
    Typed action template for D1-style decisions (§3.7).
    The Optimizer fills/refills individual slots via rule-based composition — never
    a single free-form LLM call — so every assembled Action is built only from
    slot-fillers that already passed every hard constraint.
    """
    job_order_id: str = ""
    candidate_slots: list[SlotAssignment] = []


class FlightRiskAction(Action):
    """Typed action template for D3-style flight risk decisions."""
    candidate_id: str = ""
    retention_actions: list[str] = []
    backup_candidates: list[str] = []


# SimilarPastDecision is defined above (before Action) to avoid forward-reference issues.


class Outcome(BaseModel):
    """
    Records what the human decided and what actually happened afterward.
    Feeds three things over time:
    (a) VoI priors — which evidence types mattered
    (b) Bidding weights — recalibrated from real outcomes
    (c) Per-recruiter override patterns (aggregate-only, never individual-punitive §11)
    """
    decision_id: str
    action_id: Optional[str] = None  # null for a null_no_action Outcome
    human_decision: HumanDecision
    human_edit_description: str = ""  # what was changed if edited
    downstream_result: Optional[str] = None  # e.g. "filled_in_2_days", "candidate_retained"
    predicted_confidence: float = 0.0  # recommendation's stated confidence at decision time
    was_correct: Optional[bool] = None  # did the prediction turn out right? null until resolved
    recorded_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None


class CalibrationRecord(BaseModel):
    """
    Computed periodically by the Memory/Learning Service (§3.10), not inline
    in the request path — one row per bidder per decision_type per reporting window.

    Only reported once sample_size clears a minimum threshold (§13) — same
    sample-size-guard applied to EMA weight updates.
    """
    bidder: str  # BidderType value or "Overall"
    decision_type: DecisionType
    sample_size: int
    brier_score: float  # mean((predicted_confidence - was_correct)²); lower = better calibrated
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class WeightSnapshot(BaseModel):
    """
    Logged with timestamps so a skewed update from a bad/noisy outcome
    can be inspected and rolled back (§3.10). Cheap to add, reads as operational maturity.
    """
    decision_type: DecisionType
    weights: dict[str, float]  # bidder → weight
    trigger: str  # "initial", "ema_update", "manual_override", "rollback"
    snapshot_at: datetime = Field(default_factory=datetime.utcnow)


class ClarificationQuestion(BaseModel):
    """Agent-initiated clarification (§3.9). Surfaces top-ranked unresolved gap as question."""
    decision_id: str
    gap: EvidenceGap
    question_text: str
    answered: bool = False
    answer: Optional[str] = None


class WhyNotQuery(BaseModel):
    """'Why not X' query — reads from already-computed losing bids, zero extra model calls."""
    decision_id: str
    alternative_description: str
    response: str = ""  # populated from cached bid state


# ── Confidence Propagation (§3.6) ─────────────────────────────────────────────

def compute_bidder_confidence(
    own_reasoning_confidence: float,
    cited_evidence_confidences: list[float]
) -> float:
    """
    A bidder's confidence is NOT asserted independently of the evidence it used.
    Computed as: min(own_reasoning_confidence, min(all cited evidence confidences)).

    Effect: if request proceeded as Ready-with-caveats on low-confidence evidence,
    every bid relying on that evidence is itself capped low — "proceeding with caveats"
    shows up downstream as visible uncertainty, not silent trust in shaky evidence.
    """
    if not cited_evidence_confidences:
        return own_reasoning_confidence
    return min(own_reasoning_confidence, min(cited_evidence_confidences))


# ── Pipeline State (for LangGraph) ────────────────────────────────────────────

class PipelineState(BaseModel):
    """Shared state flowing through the LangGraph execution graph."""
    # Request
    decision_request: Optional[DecisionRequest] = None
    task_plan: Optional[TaskPlan] = None

    # Evidence
    facts: list[Fact] = []
    evidence_gaps: list[EvidenceGap] = []

    # DRE
    dre_status: DREStatus = DREStatus.NOT_READY
    dre_iteration: int = 0
    max_dre_iterations: int = 3  # budget counter

    # Quality
    contradictions: list[dict] = []
    missing_info: list[str] = []

    # Bidding
    bids: list[Bid] = []
    vetoed_action_ids: list[str] = []

    # Optimizer output
    recommended_actions: list[Action] = []
    null_action: bool = False

    # Explanation
    explanation: str = ""
    counterfactuals: list[str] = []
    similar_past_decisions: list[SimilarPastDecision] = []

    # HITL
    clarification: Optional[ClarificationQuestion] = None
    awaiting_human: bool = False
    human_decision: Optional[HumanDecision] = None

    # Outcome
    outcome: Optional[Outcome] = None

    # Progress tracking (for streaming UI)
    progress_messages: list[str] = []
    current_stage: str = "initialized"
    error: Optional[str] = None
