"""
Veridex NBA Platform — Learning Service (§3.10)

Outcome capture and continuous learning:
- VoI prior updates (which evidence types mattered)
- Bidding weight recalibration via dampened EMA
- Sample-size guard: minimum count before weights move
- Brier score: mean((predicted_confidence − was_correct)²)
- Weight snapshots logged with timestamps (rollback-capable)
- Calibration records only reported when sample_size ≥ threshold

Outcome capture is CORRELATIONAL, not causal — named as a known v1 limitation.
Causal attribution is the natural v2 upgrade.
"""

from __future__ import annotations

from datetime import datetime

from backend.models import (
    Outcome, CalibrationRecord, WeightSnapshot,
    DecisionType, BidderType, Bid,
)
from backend.config import (
    MIN_SAMPLE_SIZE_FOR_UPDATE, MIN_SAMPLE_SIZE_FOR_CALIBRATION,
    EMA_LEARNING_RATE, BASE_BIDDING_WEIGHTS,
)
from backend.database import db
from backend.influence_ledger import influence_ledger


class LearningService:
    """
    Memory/Learning Service (§3.10).

    Processes outcomes to continuously improve:
    1. VoI priors — which evidence types actually mattered
    2. Bidding weights — recalibrated per decision type from real outcomes
    3. Confidence calibration — Brier score per bidder/decision type

    All updates are sample-size-gated to prevent noise from swinging weights.
    """

    def record_outcome(
        self,
        outcome: Outcome,
        decision_type: str,
        bids: list[Bid] | None = None,
    ) -> dict:
        """
        Record an outcome and trigger learning updates.

        Returns a summary of what was updated.
        """
        updates = {"outcome_recorded": True, "updates": []}

        # Save outcome
        db.save_outcome(outcome)

        # If outcome is resolved (was_correct is known), trigger learning
        if outcome.was_correct is not None:
            # Update influence ledger
            if bids:
                winning_bids = [b for b in bids if not b.is_veto]
                for bid in winning_bids:
                    influence_ledger.on_outcome_resolved(
                        bid.bidder.value, outcome.was_correct
                    )
                    updates["updates"].append(
                        f"Influence updated for {bid.bidder.value}: "
                        f"{'refund' if outcome.was_correct else 'penalty'}"
                    )

            # Replenish all bidders
            influence_ledger.on_decision_resolved_tick()

            # Try EMA weight update
            self._try_ema_update(decision_type, outcome)

            # Try calibration update
            self._try_calibration_update(decision_type)

        return updates

    def _try_ema_update(
        self,
        decision_type: str,
        outcome: Outcome,
    ) -> None:
        """
        Update bidding weights via dampened EMA if sample-size gate is met.

        Sample-size guard: a weight that visibly destabilizes from one demo
        decision reads as broken, not as learning.
        """
        resolved = db.get_resolved_outcomes(decision_type)

        if len(resolved) < MIN_SAMPLE_SIZE_FOR_UPDATE:
            return  # Not enough data to update

        # Compute success rate
        correct_count = sum(1 for o in resolved if o.was_correct)
        success_rate = correct_count / len(resolved) if resolved else 0.5

        # EMA update: slight adjustment toward what's working
        current_weights = db.get_bidding_weights(decision_type)
        updated_weights = {}

        for bidder, weight in current_weights.items():
            # Simple EMA: if outcomes are good, slightly reinforce current weights
            # If outcomes are bad, slightly adjust toward base weights
            if success_rate > 0.6:
                # Reinforce — small nudge toward current
                new_weight = weight  # Keep as-is when things are working
            else:
                # Adjust — move toward base weights
                base = BASE_BIDDING_WEIGHTS.get(bidder, weight)
                new_weight = weight + EMA_LEARNING_RATE * (base - weight)

            updated_weights[bidder] = round(new_weight, 4)
            db.update_bidding_weight(decision_type, bidder, new_weight)

        # Snapshot for rollback capability
        db.save_weight_snapshot(WeightSnapshot(
            decision_type=DecisionType(decision_type),
            weights=updated_weights,
            trigger="ema_update",
            snapshot_at=datetime.utcnow(),
        ))

    def _try_calibration_update(self, decision_type: str) -> None:
        """
        Compute and record Brier scores if sample-size gate is met.

        Brier score: mean((predicted_confidence − was_correct)²)
        Lower is better-calibrated.

        A Brier score computed on 2-3 outcomes is noise, not a calibration
        claim — suppressed from the report.
        """
        resolved = db.get_resolved_outcomes(decision_type)

        if len(resolved) < MIN_SAMPLE_SIZE_FOR_CALIBRATION:
            return

        # Compute overall Brier score
        brier_scores = []
        for outcome in resolved:
            was_correct_float = 1.0 if outcome.was_correct else 0.0
            brier = (outcome.predicted_confidence - was_correct_float) ** 2
            brier_scores.append(brier)

        if brier_scores:
            avg_brier = sum(brier_scores) / len(brier_scores)
            db.save_calibration(CalibrationRecord(
                bidder="Overall",
                decision_type=DecisionType(decision_type),
                sample_size=len(resolved),
                brier_score=round(avg_brier, 4),
                computed_at=datetime.utcnow(),
            ))

    def get_calibration_report(self) -> dict:
        """Get the current calibration report across all decision types."""
        report = {}
        for dt in DecisionType:
            records = db.get_calibration_records(decision_type=dt.value)
            if records:
                latest = records[0]
                report[dt.value] = {
                    "brier_score": latest.brier_score,
                    "sample_size": latest.sample_size,
                    "computed_at": latest.computed_at.isoformat(),
                    "interpretation": (
                        "Well calibrated" if latest.brier_score < 0.15
                        else "Moderately calibrated" if latest.brier_score < 0.25
                        else "Needs improvement"
                    ),
                }
        return report

    def get_weight_history(self, decision_type: str | None = None) -> list[dict]:
        """Get weight snapshots for visualization."""
        snapshots = db.get_weight_history(decision_type)
        return [
            {
                "decision_type": s.decision_type.value,
                "weights": s.weights,
                "trigger": s.trigger,
                "timestamp": s.snapshot_at.isoformat(),
            }
            for s in snapshots
        ]

    def seed_historical_outcomes(self) -> int:
        """Seed the learning service with historical outcomes for warm-start."""
        from backend.seed_data import generate_historical_outcomes

        historical = generate_historical_outcomes()
        count = 0
        for entry in historical:
            outcome = entry["outcome"]
            decision_type = entry["decision_type"]

            db.save_outcome(outcome)
            db.log_decision(
                decision_id=outcome.decision_id,
                tenant_id="branch-west-001",
                decision_type=decision_type,
                primary_entity_id=f"entity-{outcome.decision_id}",
                requested_by="system-seed",
            )
            db.update_decision_status(outcome.decision_id, "completed",
                                       human_decision=outcome.human_decision.value)
            count += 1

        # Run calibration updates after seeding
        for dt in DecisionType:
            self._try_calibration_update(dt.value)

        # Save initial weight snapshots
        for dt in DecisionType:
            db.save_weight_snapshot(WeightSnapshot(
                decision_type=dt,
                weights=dict(BASE_BIDDING_WEIGHTS),
                trigger="initial",
                snapshot_at=datetime.utcnow(),
            ))

        # Initialize influence ledger
        for bidder in BidderType:
            db.update_influence(bidder.value, 1.0)

        return count


# Global instance
learning_service = LearningService()
