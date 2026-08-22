"""
Veridex NBA Platform — Influence Ledger (§3.6.1)

Decaying Influence Budget — the real auction mechanic.
Built as an ADDITIVE layer over the core pipeline.

Every bidder holds influence [0.0, 1.0]:
- Winning costs influence immediately (WIN_COST)
- Correct outcomes refund partially (REFUND_GOOD)
- Wrong outcomes penalize further (PENALTY_BAD)
- Slow unconditional replenishment (REPLENISH_RATE)

Compliance is EXEMPT from influence — veto is never outbid.
"""

from __future__ import annotations

from backend.config import (
    INFLUENCE_WIN_COST, INFLUENCE_REFUND_GOOD,
    INFLUENCE_PENALTY_BAD, INFLUENCE_REPLENISH_RATE,
)
from backend.models import BidderType
from backend.database import db


class InfluenceLedger:
    """
    Influence Ledger (§3.6.1) — real auction mechanic.

    Composes with the calibration mechanism rather than duplicating it.
    A bidder with a poor Brier score is, by construction, the one whose
    wins get penalized more often via on_outcome_resolved.
    """

    def effective_weight(self, bidder: str, base_weight: float) -> float:
        """
        Compute effective weight: base_priority_weight × influence.
        Compliance is always exempt.
        """
        if bidder == BidderType.Compliance.value:
            return base_weight

        influence = db.get_influence(bidder)
        return base_weight * influence

    def on_slot_won(self, bidder: str) -> None:
        """
        Winning costs influence, immediately.
        Getting your way is not free — this is the actual scarcity mechanic.
        """
        if bidder == BidderType.Compliance.value:
            return

        current = db.get_influence(bidder)
        new_influence = max(0.0, current - INFLUENCE_WIN_COST)
        db.update_influence(bidder, new_influence)
        db.record_win(bidder)

    def on_outcome_resolved(self, bidder: str, was_correct: bool) -> None:
        """
        Outcomes settle the debt:
        - Correct call → partial refund
        - Wrong call → additional penalty (no refund)
        """
        if bidder == BidderType.Compliance.value:
            return

        current = db.get_influence(bidder)
        if was_correct:
            new_influence = min(1.0, current + INFLUENCE_REFUND_GOOD)
        else:
            new_influence = max(0.0, current - INFLUENCE_PENALTY_BAD)
        db.update_influence(bidder, new_influence)

    def on_decision_resolved_tick(self) -> None:
        """
        Slow, unconditional replenishment for every bidder.
        Called for every resolved decision, regardless of outcome.

        Prevents permanent lock-out of legitimately-cautious bidders.
        """
        for bidder in BidderType:
            if bidder == BidderType.Compliance:
                continue
            current = db.get_influence(bidder.value)
            new_influence = min(1.0, current + INFLUENCE_REPLENISH_RATE)
            db.update_influence(bidder.value, new_influence)

    def get_all_influences(self) -> dict[str, float]:
        """Get current influence values for all bidders."""
        return db.get_all_influences()


# Global instance
influence_ledger = InfluenceLedger()
