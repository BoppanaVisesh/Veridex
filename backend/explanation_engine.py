"""
Veridex NBA Platform — Explanation & Counterfactual Engine (§3.8)

Generates:
- Supporting evidence with source + confidence from shared memory (no fabrication)
- Losing bids and why they lost
- Counterfactuals: "if X were confirmed, this option would have ranked #1 instead"
- Precedent: similar past decisions surfaced alongside evidence

CONSTRAINT: can only cite evidence_refs already in state (prevents hallucinated evidence).
"""

from __future__ import annotations

from backend.models import (
    Action, Bid, Fact, SimilarPastDecision, BidderType,
)


class ExplanationEngine:
    """
    Explanation & Counterfactual Engine (§3.8).

    Precedent is part of the explanation, not just the evidence base.
    "Here's the evidence AND here's what happened last time this looked like this."
    """

    def generate_explanation(
        self,
        action: Action,
        all_bids: list[Bid],
        facts: list[Fact],
        similar_past: list[SimilarPastDecision] | None = None,
        contradictions: list[dict] | None = None,
        missing_info: list[str] | None = None,
    ) -> Action:
        """
        Generate full explanation for the recommended action.

        Modifies the action in-place with explanation, counterfactuals,
        similar past cases, and losing bid summaries.
        """
        # 1. Build evidence summary (only citing refs in state)
        evidence_summary = self._build_evidence_summary(facts, all_bids)

        # 2. Build losing bids summary
        winning_bidder_ids = set(action.composed_from)
        losing_bids = [b for b in all_bids if b.id not in winning_bidder_ids and not b.is_veto]
        losing_summary = self._build_losing_summary(losing_bids)

        # 3. Generate counterfactuals
        counterfactuals = self._generate_counterfactuals(all_bids, facts)

        # 4. Precedent context
        precedent_text = self._build_precedent_context(similar_past or [])

        # 5. Compose full explanation
        explanation_parts = [
            "## Recommendation Rationale\n",
            action.description,
            "\n\n## Supporting Evidence\n",
            evidence_summary,
        ]

        if precedent_text:
            explanation_parts.extend([
                "\n\n## Similar Past Decisions\n",
                precedent_text,
            ])

        if losing_summary:
            explanation_parts.extend([
                "\n\n## Alternative Options Considered\n",
                losing_summary,
            ])

        if counterfactuals:
            explanation_parts.extend([
                "\n\n## What Would Change This Recommendation\n",
                "\n".join(f"• {cf}" for cf in counterfactuals),
            ])

        if contradictions:
            explanation_parts.extend([
                "\n\n## ⚠️ Evidence Contradictions\n",
                "\n".join(f"• {c['description']}" for c in contradictions),
            ])

        if missing_info:
            explanation_parts.extend([
                "\n\n## ℹ️ Missing Information\n",
                "\n".join(f"• {m}" for m in missing_info),
            ])

        action.explanation = "\n".join(explanation_parts)
        action.counterfactuals = counterfactuals
        action.similar_past_cases = similar_past or []
        action.contradictions = [c.get("description", str(c)) for c in (contradictions or [])]
        action.missing_info = missing_info or []

        # Build losing bids for "Why not X" queries
        action.losing_bids_summary = [
            {
                "bidder": b.bidder.value,
                "score": round(b.score, 2),
                "rationale": b.rationale,
                "confidence": round(b.confidence, 2),
                "evidence_refs": b.evidence_refs,
            }
            for b in losing_bids
        ]

        return action

    def _build_evidence_summary(
        self,
        facts: list[Fact],
        bids: list[Bid],
    ) -> str:
        """Build evidence summary citing only refs already in state."""
        # Collect all evidence refs cited by bids
        cited_refs = set()
        for bid in bids:
            cited_refs.update(bid.evidence_refs)

        # Build summary grouped by source
        by_source: dict[str, list[Fact]] = {}
        for f in facts:
            if not cited_refs or f.evidence_ref in cited_refs or f.source_agent == "Catalog_Evidence_Agent":
                source = f.source_agent
                if source not in by_source:
                    by_source[source] = []
                by_source[source].append(f)

        # If cited_refs matched nothing, include all facts up to cap
        if not by_source and facts:
            for f in facts:
                source = f.source_agent
                if source not in by_source:
                    by_source[source] = []
                by_source[source].append(f)

        parts = []
        for source, source_facts in by_source.items():
            parts.append(f"\n**{source}:**")
            for f in source_facts[:5]:  # Cap at 5 per source for readability
                conf_bar = "🟢" if f.confidence >= 0.8 else "🟡" if f.confidence >= 0.6 else "🔴"
                parts.append(
                    f"  {conf_bar} [{f.confidence:.0%}] {f.fact_type}: {str(f.value)[:150]}"
                    f"\n    _Source: {f.evidence_ref}_"
                )

        return "\n".join(parts) if parts else "No specific evidence cited."

    def _build_losing_summary(self, losing_bids: list[Bid]) -> str:
        """Build summary of losing bids for transparency."""
        if not losing_bids:
            return ""

        parts = []
        for bid in sorted(losing_bids, key=lambda b: b.score, reverse=True):
            parts.append(
                f"• **{bid.bidder.value}** (score: {bid.score:.2f}, confidence: {bid.confidence:.0%}): "
                f"{bid.rationale[:200]}"
            )
        return "\n".join(parts)

    def _generate_counterfactuals(
        self,
        bids: list[Bid],
        facts: list[Fact],
    ) -> list[str]:
        """
        Generate counterfactuals: "if X were confirmed, this would change."

        These help the human understand what evidence would change the outcome.
        """
        counterfactuals = []

        # Find compliance vetoes and what would change
        vetoes = [b for b in bids if b.is_veto]
        for v in vetoes:
            counterfactuals.append(
                f"If {v.veto_reason.split('(')[0].strip()} were resolved, "
                f"this option would be reconsidered in scoring."
            )

        # Find low-confidence facts that could swing the decision
        low_conf_facts = [f for f in facts if 0.3 < f.confidence < 0.7]
        for f in low_conf_facts[:2]:
            counterfactuals.append(
                f"If '{f.fact_type}' were confirmed (currently {f.confidence:.0%} confidence), "
                f"this could change the recommendation's confidence level."
            )

        # Find close competing scores
        non_veto_bids = [b for b in bids if not b.is_veto]
        if len(non_veto_bids) >= 2:
            sorted_bids = sorted(non_veto_bids, key=lambda b: b.score, reverse=True)
            top, second = sorted_bids[0], sorted_bids[1]
            if abs(top.score - second.score) < 0.15:
                counterfactuals.append(
                    f"The {second.bidder.value} perspective (score: {second.score:.2f}) is close to "
                    f"{top.bidder.value} (score: {top.score:.2f}) — a small shift in evidence "
                    f"could change which objective is prioritized."
                )

        return counterfactuals

    def _build_precedent_context(
        self,
        similar_past: list[SimilarPastDecision],
    ) -> str:
        """
        Build precedent context (§3.8).

        "3 similar D3 cases in the last 90 days — 2 retained after a same-day call,
        1 left anyway" is shown next to the recommendation.
        """
        if not similar_past:
            return ""

        parts = [f"**{len(similar_past)} similar past decisions found:**\n"]
        for sp in similar_past:
            parts.append(
                f"• [{sp.similarity_score:.0%} match] **{sp.decision_id}**: "
                f"Action taken: {sp.action_taken_summary}. "
                f"Outcome: {sp.outcome_summary}"
            )

        # Summary pattern
        outcomes = [sp.outcome_summary.lower() for sp in similar_past]
        positive = sum(1 for o in outcomes if any(w in o for w in ["retained", "filled", "renewed", "placed", "accepted"]))
        total = len(outcomes)
        if total > 0:
            parts.append(f"\n_Pattern: {positive}/{total} had positive outcomes._")

        return "\n".join(parts)

    def handle_why_not_x(
        self,
        alternative_description: str,
        all_bids: list[Bid],
        action: Action,
    ) -> str:
        """
        Handle "Why not X" query (§3.9).

        Zero extra model calls — reads from already-computed bid state.
        Guaranteed-instant UI interaction, not something that "thinks" again.
        """
        # Find the most relevant losing bid
        response_parts = [
            f'## Why not: "{alternative_description}"\n',
        ]

        # Check each bidder's perspective on the alternative
        for bid in all_bids:
            if bid.is_veto:
                response_parts.append(
                    f"**{bid.bidder.value} (VETO)**: {bid.veto_reason}"
                )
            else:
                response_parts.append(
                    f"**{bid.bidder.value}** (score: {bid.score:.2f}): {bid.rationale}"
                )

        response_parts.append(
            f"\n**Current recommendation score: {action.aggregate_score:.2f}**"
        )
        response_parts.append(
            "The recommended action was selected because it optimally balanced "
            "all bidder perspectives while respecting compliance constraints."
        )

        return "\n".join(response_parts)


# Global instance
explanation_engine = ExplanationEngine()
