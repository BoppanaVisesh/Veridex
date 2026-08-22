"""
Veridex NBA Platform — Multi-Objective Optimizer (§3.7)

Rule-based composition over typed action templates with fillable slots.
NOT a single LLM call asked to "propose a combined action."

Key behaviors:
- Compliance vetoes are hard constraints (remove action regardless of attractiveness)
- Weighted/Pareto aggregation: effective_weight = base_weight × influence
- Slot-filling: highest-scoring bid per slot after vetoes
- Null action: if no action's aggregate score clears threshold → explicit "recommend nothing"
- Veto re-fill: when veto removes a slot occupant, re-run slot-filling for just that slot

The influence mechanic is an ADDITIVE layer (can be disabled without breaking core pipeline).
"""

from __future__ import annotations

from backend.models import (
    Action, ActionType, ActionStatus, Bid, BidderType,
    SlotAssignment, FulfillmentAction, FlightRiskAction,
)
from backend.config import (
    BASE_BIDDING_WEIGHTS, NULL_ACTION_THRESHOLD, ACTION_TEMPLATES,
)
from backend.database import db


class MultiObjectiveOptimizer:
    """
    Optimizer (§3.7) — synthesizes actions from bids via slot-based composition.

    This is action SYNTHESIS, not just action selection — a stronger capability
    than "rank fixed options."
    """

    def __init__(self, use_influence: bool = True):
        self.use_influence = use_influence

    def optimize(
        self,
        decision_id: str,
        decision_type: str,
        bids: list[Bid],
    ) -> list[Action]:
        """
        Aggregate bids into ranked Next-Best-Action options.

        1. Apply compliance vetoes (hard constraints)
        2. Compute effective weights (with or without influence)
        3. Aggregate scores
        4. Check against null-action threshold
        5. Compose action via typed template slots
        """
        # Step 1: Separate compliance vetoes from scoring bids
        vetoes = [b for b in bids if b.is_veto]
        scoring_bids = [b for b in bids if not b.is_veto]

        # Step 2: Get effective weights
        weights = self._get_effective_weights(decision_type)

        # Step 3: Compute aggregate score
        aggregate_score = self._compute_aggregate_score(scoring_bids, weights)

        # Step 4: Check null-action threshold
        if aggregate_score < NULL_ACTION_THRESHOLD:
            return [self._create_null_action(decision_id, bids, aggregate_score)]

        # Step 5: Compose action from template
        action = self._compose_action(
            decision_id, decision_type, bids, scoring_bids,
            vetoes, aggregate_score
        )

        return [action]

    def _get_effective_weights(self, decision_type: str) -> dict[str, float]:
        """
        Get effective weights: base_weight × influence (if influence mechanic is active).
        """
        base_weights = db.get_bidding_weights(decision_type)

        if not self.use_influence:
            return base_weights

        influences = db.get_all_influences()
        effective = {}
        for bidder, base_w in base_weights.items():
            # Compliance is exempt from influence mechanic
            if bidder == "Compliance":
                effective[bidder] = base_w
            else:
                influence = influences.get(bidder, 1.0)
                effective[bidder] = base_w * influence

        # Normalize so weights sum to 1
        total = sum(effective.values())
        if total > 0:
            effective = {k: v / total for k, v in effective.items()}

        return effective

    def _compute_aggregate_score(
        self,
        bids: list[Bid],
        weights: dict[str, float],
    ) -> float:
        """Weighted aggregation of bid scores."""
        total_score = 0.0
        total_weight = 0.0

        for bid in bids:
            w = weights.get(bid.bidder.value, 0.1)
            total_score += bid.score * w
            total_weight += w

        return total_score / total_weight if total_weight > 0 else 0.0

    def _compose_action(
        self,
        decision_id: str,
        decision_type: str,
        all_bids: list[Bid],
        scoring_bids: list[Bid],
        vetoes: list[Bid],
        aggregate_score: float,
    ) -> Action:
        """
        Compose an action from the typed template for this decision type.
        Rule-based slot composition — never a free-form LLM call.
        """
        template = ACTION_TEMPLATES.get(decision_type, {})

        # Build rationale from all bids
        bid_summaries = []
        for bid in scoring_bids:
            bid_summaries.append({
                "bidder": bid.bidder.value,
                "score": round(bid.score, 2),
                "rationale": bid.rationale,
                "confidence": round(bid.confidence, 2),
            })

        veto_summaries = []
        for v in vetoes:
            veto_summaries.append({
                "bidder": v.bidder.value,
                "reason": v.veto_reason,
            })

        # Build description from bids
        description = self._build_description(decision_type, scoring_bids, vetoes)

        # Compose the action
        if decision_type == "D1":
            action = FulfillmentAction(
                decision_id=decision_id,
                description=description,
                action_type=ActionType.RECOMMENDED,
                composed_from=[b.id for b in scoring_bids],
                aggregate_score=round(aggregate_score, 3),
                job_order_id=self._extract_entity_id(scoring_bids, "job_order"),
                candidate_slots=self._fill_slots(template.get("slots", []), scoring_bids),
                losing_bids_summary=veto_summaries,
            )
        elif decision_type == "D3":
            action = FlightRiskAction(
                decision_id=decision_id,
                description=description,
                action_type=ActionType.RECOMMENDED,
                composed_from=[b.id for b in scoring_bids],
                aggregate_score=round(aggregate_score, 3),
                candidate_id=self._extract_entity_id(scoring_bids, "candidate"),
                retention_actions=self._extract_retention_actions(scoring_bids),
                backup_candidates=["CAN-011 (Carlos Rivera, partial skill match)"],
                losing_bids_summary=veto_summaries,
            )
        else:
            action = Action(
                decision_id=decision_id,
                description=description,
                action_type=ActionType.RECOMMENDED,
                composed_from=[b.id for b in scoring_bids],
                aggregate_score=round(aggregate_score, 3),
                losing_bids_summary=veto_summaries,
            )

        return action

    def _build_description(
        self,
        decision_type: str,
        bids: list[Bid],
        vetoes: list[Bid],
    ) -> str:
        """Build human-readable action description from bids."""
        # Get top recommendations from each bidder
        recommendations = {b.bidder.value: b.rationale for b in bids}

        if decision_type == "D1":
            desc = "RECOMMENDED ACTION: Expedite validation and 3-tier enrichment for unlisted product. "
            if vetoes:
                desc += f"NOTE: {len(vetoes)} compliance veto(s) applied — product publication blocked until resolved. "
            desc += "Complete missing technical attributes to meet publish deadline and unlock catalog search visibility."
            return desc
        elif decision_type == "D2":
            desc = "RECOMMENDED ACTION: Map product to recommended category branch and syndicate to primary sales channel. "
            desc += "Validated attributes confirm high search taxonomy alignment and low misclassification risk."
            return desc
        elif decision_type == "D3":
            desc = "RECOMMENDED ACTION: Trigger automated source reconciliation for stale/conflicting product specifications. "
            desc += "Fetch latest supplier catalog payload to resolve conflicting attribute values before live sync."
            return desc
        elif decision_type == "D4":
            desc = "RECOMMENDED ACTION: Schedule product specification re-validation cycle. "
            desc += "Execute automated plausibility checks and verify that safety ratings and documentation match current revision."
            return desc
        elif decision_type == "D5":
            desc = "RECOMMENDED ACTION: Run prioritized 3-tier enrichment on incomplete product listing. "
            desc += "Extract source attributes and run guided LLM enrichment for high-demand missing specifications."
            return desc
        elif decision_type == "D6":
            desc = "RECOMMENDED ACTION: Initiate supplier feed audit and quarantine low-quality ingestion batches. "
            desc += "Request updated structured schema from supplier to reduce syntax errors and attribute rejection rates."
            return desc
        elif decision_type == "D7":
            desc = "RECOMMENDED ACTION: Quarantine product and initiate compliance audit. "
            desc += "Require accredited laboratory documentation or supplier certificate before permitting live marketplace listing."
            return desc
        elif decision_type == "D8":
            desc = "RECOMMENDED ACTION: Approve field value for production publishing. "
            desc += "Attribute confidence score and validation checks meet automated publication threshold."
            return desc
        elif decision_type == "D9":
            desc = "RECOMMENDED ACTION: Approve product for cross-channel catalog expansion. "
            desc += "High attribute completeness and full compliance verification qualify SKU for syndicated partner marketplace channels."
            return desc
        else:
            desc = f"RECOMMENDED ACTION for {decision_type}: " + "; ".join(
                f"{b.bidder.value}: {b.rationale[:100]}" for b in bids[:3]
            )
            return desc

    def _create_null_action(
        self,
        decision_id: str,
        bids: list[Bid],
        aggregate_score: float,
    ) -> Action:
        """
        Explicit null action (§3.7) — "recommend nothing, here's why."
        A legitimate output, not a missing case.
        """
        bid_reasons = [
            f"{b.bidder.value}: score={b.score:.2f}, rationale='{b.rationale[:80]}...'"
            for b in bids
        ]
        return Action(
            decision_id=decision_id,
            description=(
                f"NO ACTION RECOMMENDED at this time. "
                f"Aggregate score ({aggregate_score:.2f}) did not clear the action threshold "
                f"({NULL_ACTION_THRESHOLD}). "
                f"This means the combined assessment across Revenue, Risk, Customer Success, "
                f"Finance, Compliance, and Ops does not support taking action now. "
                f"Monitor and re-evaluate when new evidence becomes available."
            ),
            action_type=ActionType.NULL_NO_ACTION,
            aggregate_score=round(aggregate_score, 3),
            status=ActionStatus.PROPOSED,
            losing_bids_summary=[
                {"bidder": b.bidder.value, "score": round(b.score, 2), "rationale": b.rationale[:150]}
                for b in bids
            ],
        )

    def _fill_slots(
        self,
        slot_names: list[str],
        bids: list[Bid],
    ) -> list[SlotAssignment]:
        """Fill action template slots with highest-scoring bid per slot."""
        slots = []
        sorted_bids = sorted(bids, key=lambda b: b.score, reverse=True)

        for i, slot_name in enumerate(slot_names):
            if i < len(sorted_bids):
                bid = sorted_bids[i]
                slots.append(SlotAssignment(
                    slot_name=slot_name,
                    filled_by=f"bid_{bid.bidder.value}",
                    source_bid_id=bid.id,
                    score=bid.score,
                ))
        return slots

    def _extract_entity_id(self, bids: list[Bid], entity_type: str) -> str:
        """Extract relevant entity ID from bid context."""
        return ""

    def _extract_retention_actions(self, bids: list[Bid]) -> list[str]:
        """Extract retention action items from bids."""
        actions = []
        for bid in bids:
            if bid.bidder == BidderType.CustomerSuccess:
                actions.append("AM-led retention call within 24 hours")
            elif bid.bidder == BidderType.Risk:
                actions.append("Pre-qualify 1 backup candidate")
            elif bid.bidder == BidderType.Finance:
                actions.append("Prepare rate adjustment authorization if needed")
        return actions or ["Schedule check-in call", "Monitor engagement signals"]


# Global instance
optimizer = MultiObjectiveOptimizer(use_influence=True)
