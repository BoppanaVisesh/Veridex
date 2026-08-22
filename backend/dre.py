"""
Veridex NBA Platform — Decision Readiness Evaluator (§3.4) + Detectors (§3.5)

DRE:
- Evidence Gap Analysis against decision-type checklists
- 4-state output: Ready, Not-Ready, Ready-with-caveats, Blocked
- VoI ranking: weight × (1 − current_confidence) — highest goes first
- Budget counter to cap iterations

Detectors:
- Contradiction Detector: flags conflicting facts, caps confidence, can flip Ready→Not-Ready
- Missing-Info Detector: flags structurally required-but-absent facts
Both feed the same gap-list/VoI machinery.
"""

from __future__ import annotations

from backend.models import (
    DREStatus, EvidenceGap, Fact, DecisionType, PipelineState
)
from backend.config import (
    DECISION_CHECKLISTS, DRE_CONFIDENCE_THRESHOLD,
    DRE_READINESS_THRESHOLD, DRE_CAVEATS_THRESHOLD,
    MAX_DRE_ITERATIONS,
)
from backend.memory_graph import SharedEvidenceMemory


class DecisionReadinessEvaluator:
    """
    DRE (§3.4) — decides whether enough evidence exists before the bidding layer runs.

    If not enough evidence:
    - Identifies gaps via checklist comparison
    - Ranks gaps by VoI: weight × (1 − current_confidence)
    - Returns top gap for Dynamic Agent Creator to fetch

    States:
    - Ready: all checklist items have sufficient confidence
    - Not-Ready: gaps exist, more evidence needed (loop back)
    - Ready-with-caveats: proceed but flag residual uncertainty for agent-initiated clarification
    - Blocked: compliance gap with no caveat-path → hard exit to human escalation
    """

    def evaluate(
        self,
        facts: list[Fact],
        decision_type: str,
        decision_id: str,
        contradictions: list[dict] | None = None,
    ) -> tuple[DREStatus, list[EvidenceGap]]:
        """
        Evaluate decision readiness.

        Returns (status, gaps) where gaps are sorted by VoI score descending.
        """
        checklist = DECISION_CHECKLISTS.get(decision_type, [])
        if not checklist:
            return DREStatus.READY, []

        # Build confidence map from available facts
        # Keep highest confidence per fact_type across all sources
        confidence_map: dict[str, float] = {}
        for fact in facts:
            current = confidence_map.get(fact.fact_type, 0.0)
            effective_confidence = fact.confidence

            # If fact has a contradiction flagged, cap its effective confidence
            if contradictions:
                for c in contradictions:
                    if c.get("fact_type") == fact.fact_type:
                        effective_confidence = min(effective_confidence, 0.4)
                        break

            confidence_map[fact.fact_type] = max(current, effective_confidence)

        # Compute gaps
        gaps: list[EvidenceGap] = []
        has_compliance_gap = False
        total_weight = 0.0
        weighted_confidence = 0.0

        for item in checklist:
            ft = item["fact_type"]
            conf = confidence_map.get(ft, 0.0)
            weight = item["weight"]
            is_compliance = item.get("compliance", False)

            total_weight += weight
            weighted_confidence += weight * conf

            if conf < DRE_CONFIDENCE_THRESHOLD:
                gap = EvidenceGap(
                    decision_id=decision_id,
                    fact_type=ft,
                    checklist_weight=weight,
                    current_confidence=conf,
                    is_compliance_relevant=is_compliance,
                )
                gap.compute_voi()
                gaps.append(gap)

                if is_compliance and conf < 0.3:
                    has_compliance_gap = True

        # Sort by VoI descending
        gaps.sort(key=lambda g: g.voi_score, reverse=True)

        # Determine status
        readiness_score = weighted_confidence / total_weight if total_weight > 0 else 0.0

        if has_compliance_gap:
            # Check if compliance gap is unresolvable
            compliance_gaps = [g for g in gaps if g.is_compliance_relevant]
            if any(g.current_confidence == 0.0 for g in compliance_gaps):
                return DREStatus.BLOCKED, gaps
            return DREStatus.NOT_READY, gaps

        if readiness_score >= DRE_READINESS_THRESHOLD:
            if gaps:
                return DREStatus.READY_WITH_CAVEATS, gaps
            return DREStatus.READY, gaps
        elif readiness_score >= DRE_CAVEATS_THRESHOLD:
            return DREStatus.READY_WITH_CAVEATS, gaps
        else:
            return DREStatus.NOT_READY, gaps


class ContradictionDetector:
    """
    Contradiction Detector (§3.5) — flags conflicting facts.

    A confirmed contradiction:
    (a) caps the contradicted fact's effective confidence
    (b) can flip Ready→Not-Ready if the fact is checklist-critical

    Contradictions are surfaced to the human, NEVER silently resolved.
    """

    def detect(self, facts: list[Fact]) -> list[dict]:
        """Find contradictions in the evidence."""
        from collections import defaultdict

        # Group facts by entity_id + fact_type
        groups: dict[str, list[Fact]] = defaultdict(list)
        for f in facts:
            key = f"{f.entity_id}:{f.fact_type}"
            groups[key].append(f)

        contradictions = []
        for key, group_facts in groups.items():
            if len(group_facts) < 2:
                continue

            sorted_facts = sorted(group_facts, key=lambda f: f.timestamp)
            for i in range(len(sorted_facts)):
                for j in range(i + 1, len(sorted_facts)):
                    f1, f2 = sorted_facts[i], sorted_facts[j]
                    # Compare values — simple string comparison for now
                    if str(f1.value).strip().lower() != str(f2.value).strip().lower():
                        # Check if they're substantively different (not just formatting)
                        if self._is_substantive_contradiction(f1, f2):
                            contradictions.append({
                                "entity_id": f1.entity_id,
                                "fact_type": f1.fact_type,
                                "fact_1_source": f1.source_agent,
                                "fact_1_value": str(f1.value)[:200],
                                "fact_1_confidence": f1.confidence,
                                "fact_2_source": f2.source_agent,
                                "fact_2_value": str(f2.value)[:200],
                                "fact_2_confidence": f2.confidence,
                                "description": (
                                    f"⚠️ Contradiction on {f1.fact_type}: "
                                    f"{f1.source_agent} says '{str(f1.value)[:80]}...' "
                                    f"but {f2.source_agent} says '{str(f2.value)[:80]}...'"
                                ),
                            })
        return contradictions

    def _is_substantive_contradiction(self, f1: Fact, f2: Fact) -> bool:
        """Check if two facts are substantively contradictory, not just different wording."""
        # Different sources with different values = potential contradiction
        if f1.source_agent != f2.source_agent:
            v1 = str(f1.value).lower()
            v2 = str(f2.value).lower()
            # Check for clear opposites
            opposites = [
                ("positive", "negative"), ("high", "low"),
                ("cleared", "pending"), ("active", "withdrawn"),
                ("satisfied", "frustrated"), ("growing", "declining"),
            ]
            for a, b in opposites:
                if (a in v1 and b in v2) or (b in v1 and a in v2):
                    return True
            # If values are substantially different text, flag it
            if len(set(v1.split()) & set(v2.split())) / max(len(v1.split()), len(v2.split()), 1) < 0.3:
                return True
        return False


class MissingInfoDetector:
    """
    Missing-Info Detector (§3.5) — flags structurally required-but-absent facts
    even if the DRE already proceeded.

    Belt-and-suspenders visibility for the human reviewer.
    Findings feed the same gap-list/VoI machinery.
    """

    def detect(
        self,
        facts: list[Fact],
        decision_type: str,
    ) -> list[str]:
        """Find missing required information."""
        checklist = DECISION_CHECKLISTS.get(decision_type, [])
        if not checklist:
            return []

        available = {f.fact_type for f in facts}
        missing = []

        for item in checklist:
            if item["fact_type"] not in available:
                severity = "CRITICAL" if item.get("compliance") else "Advisory"
                missing.append(
                    f"[{severity}] Missing: {item['fact_type']} "
                    f"(weight: {item['weight']}, "
                    f"compliance-relevant: {item.get('compliance', False)})"
                )

        return missing


# Global instances
dre = DecisionReadinessEvaluator()
contradiction_detector = ContradictionDetector()
missing_info_detector = MissingInfoDetector()
