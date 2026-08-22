"""
Veridex NBA Platform — Shared Evidence Memory Graph (§3.3)

NetworkX-based in-memory graph storing entities and facts.
- Entity nodes: Client, JobOrder, Candidate, Contract, Recruiter
- Facts stored as typed tuples: (value, source, confidence, timestamp, evidence_ref)
- All queries are tenant-scoped (§6, §11) — never global scans
- PII access control via pii_class filtering (§11)
- Contradiction detection helpers
- Missing-info detection against decision-type checklists
"""

from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime
from typing import Optional

import networkx as nx

from backend.models import (
    EntityType, Fact, EvidenceGap, PIIClass, DecisionType
)
from backend.config import DECISION_CHECKLISTS, DRE_CONFIDENCE_THRESHOLD


class SharedEvidenceMemory:
    """
    Thread-safe shared evidence memory graph.

    Entities are nodes, facts are edges from entity to a fact-node.
    Every node and fact carries tenant_id for multi-tenancy scoping.
    """

    def __init__(self):
        self._graph = nx.DiGraph()
        self._facts: dict[str, list[Fact]] = defaultdict(list)  # entity_id → facts
        self._all_facts: list[Fact] = []
        self._lock = threading.RLock()

    # ── Entity Management ──────────────────────────────────────────────────

    def add_entity(self, entity_type: EntityType, entity_id: str,
                   tenant_id: str, attributes: dict | None = None) -> None:
        """Add or update an entity node."""
        with self._lock:
            self._graph.add_node(
                entity_id,
                entity_type=entity_type.value,
                tenant_id=tenant_id,
                **(attributes or {})
            )

    def get_entity(self, entity_id: str, tenant_id: str) -> dict | None:
        """Get entity attributes, tenant-scoped."""
        with self._lock:
            if entity_id in self._graph.nodes:
                node = self._graph.nodes[entity_id]
                if node.get("tenant_id") == tenant_id:
                    return dict(node)
            return None

    def get_entities_by_type(self, entity_type: EntityType,
                              tenant_id: str) -> list[dict]:
        """List entities of a given type within a tenant."""
        with self._lock:
            results = []
            for node_id, data in self._graph.nodes(data=True):
                if (data.get("entity_type") == entity_type.value
                        and data.get("tenant_id") == tenant_id):
                    results.append({"id": node_id, **data})
            return results

    # ── Fact Management ────────────────────────────────────────────────────

    def add_fact(self, fact: Fact) -> None:
        """
        Write a fact into the evidence memory graph.

        The fact is stored both as a graph edge (entity→fact_node) and
        in an indexed list for fast retrieval by entity or fact_type.
        """
        with self._lock:
            # Ensure entity node exists
            if fact.entity_id not in self._graph.nodes:
                self.add_entity(
                    fact.entity_type, fact.entity_id,
                    fact.tenant_id
                )

            # Create fact node
            fact_node_id = f"fact_{fact.id}"
            self._graph.add_node(
                fact_node_id,
                node_type="fact",
                fact_type=fact.fact_type,
                value=fact.value,
                source_agent=fact.source_agent,
                confidence=fact.confidence,
                timestamp=fact.timestamp.isoformat(),
                evidence_ref=fact.evidence_ref,
                tenant_id=fact.tenant_id,
                pii_class=fact.pii_class.value,
            )

            # Edge from entity to fact
            self._graph.add_edge(fact.entity_id, fact_node_id,
                                  fact_type=fact.fact_type)

            # Index
            self._facts[fact.entity_id].append(fact)
            self._all_facts.append(fact)

    def add_facts(self, facts: list[Fact]) -> None:
        """Batch-write facts."""
        for fact in facts:
            self.add_fact(fact)

    def get_facts_for_entity(
        self,
        entity_id: str,
        tenant_id: str,
        fact_type: str | None = None,
        pii_access_level: PIIClass = PIIClass.NONE,
    ) -> list[Fact]:
        """
        Retrieve facts for an entity, tenant-scoped with PII filtering.

        pii_access_level controls what the caller can see:
        - NONE: only non-PII facts
        - STANDARD: none + standard PII
        - SENSITIVE: all facts (requires compliance/manager role)
        """
        with self._lock:
            allowed_levels = {PIIClass.NONE}
            if pii_access_level == PIIClass.STANDARD:
                allowed_levels.add(PIIClass.STANDARD)
            elif pii_access_level == PIIClass.SENSITIVE:
                allowed_levels.update({PIIClass.STANDARD, PIIClass.SENSITIVE})

            results = []
            for fact in self._facts.get(entity_id, []):
                if fact.tenant_id != tenant_id:
                    continue
                if fact.pii_class not in allowed_levels:
                    continue
                if fact_type and fact.fact_type != fact_type:
                    continue
                results.append(fact)
            return results

    def get_all_facts_for_decision(
        self,
        entity_ids: list[str],
        tenant_id: str,
        pii_access_level: PIIClass = PIIClass.SENSITIVE,
    ) -> list[Fact]:
        """Get all facts across multiple entities for a decision context."""
        all_facts = []
        for entity_id in entity_ids:
            all_facts.extend(
                self.get_facts_for_entity(entity_id, tenant_id,
                                           pii_access_level=pii_access_level)
            )
        return all_facts

    def get_facts_by_type(
        self,
        fact_type: str,
        tenant_id: str,
    ) -> list[Fact]:
        """Get all facts of a given type within a tenant."""
        with self._lock:
            return [
                f for f in self._all_facts
                if f.fact_type == fact_type and f.tenant_id == tenant_id
            ]

    def get_latest_fact(
        self,
        entity_id: str,
        fact_type: str,
        tenant_id: str,
    ) -> Fact | None:
        """Get the most recent fact of a given type for an entity."""
        facts = self.get_facts_for_entity(
            entity_id, tenant_id, fact_type=fact_type,
            pii_access_level=PIIClass.SENSITIVE
        )
        if not facts:
            return None
        return max(facts, key=lambda f: f.timestamp)

    # ── Contradiction Detection (§3.5) ─────────────────────────────────────

    def detect_contradictions(
        self,
        entity_id: str,
        tenant_id: str,
    ) -> list[dict]:
        """
        Flag conflicting facts on the same entity+fact_type.

        A contradiction is surfaced to the human, NEVER silently resolved.
        A confirmed contradiction:
        (a) caps the contradicted fact's effective confidence
        (b) can flip Ready→Not-Ready if the fact is checklist-critical
        """
        with self._lock:
            facts = self.get_facts_for_entity(
                entity_id, tenant_id,
                pii_access_level=PIIClass.SENSITIVE
            )

            # Group by fact_type
            by_type: dict[str, list[Fact]] = defaultdict(list)
            for f in facts:
                by_type[f.fact_type].append(f)

            contradictions = []
            for fact_type, type_facts in by_type.items():
                if len(type_facts) < 2:
                    continue

                # Sort by timestamp to find latest vs older
                sorted_facts = sorted(type_facts, key=lambda f: f.timestamp)

                # Check for value disagreements
                for i in range(len(sorted_facts)):
                    for j in range(i + 1, len(sorted_facts)):
                        f1, f2 = sorted_facts[i], sorted_facts[j]
                        if str(f1.value).lower() != str(f2.value).lower():
                            contradictions.append({
                                "entity_id": entity_id,
                                "fact_type": fact_type,
                                "fact_1": {
                                    "value": f1.value,
                                    "source": f1.source_agent,
                                    "confidence": f1.confidence,
                                    "timestamp": f1.timestamp.isoformat(),
                                    "evidence_ref": f1.evidence_ref,
                                },
                                "fact_2": {
                                    "value": f2.value,
                                    "source": f2.source_agent,
                                    "confidence": f2.confidence,
                                    "timestamp": f2.timestamp.isoformat(),
                                    "evidence_ref": f2.evidence_ref,
                                },
                                "description": (
                                    f"Contradiction on {fact_type}: "
                                    f"{f1.source_agent} says '{f1.value}' "
                                    f"but {f2.source_agent} says '{f2.value}'"
                                ),
                            })
            return contradictions

    # ── Missing-Info Detection (§3.5) ──────────────────────────────────────

    def detect_missing_info(
        self,
        entity_ids: list[str],
        decision_type: str,
        tenant_id: str,
    ) -> list[EvidenceGap]:
        """
        Flag structurally required-but-absent facts for a decision type.

        Feeds the same gap-list/VoI machinery used in §3.4 —
        there's one gap list, populated by both readiness-checking and continuous monitoring.
        """
        checklist = DECISION_CHECKLISTS.get(decision_type, [])
        if not checklist:
            return []

        # Collect all available fact types
        available_facts: dict[str, float] = {}
        for entity_id in entity_ids:
            facts = self.get_facts_for_entity(
                entity_id, tenant_id,
                pii_access_level=PIIClass.SENSITIVE
            )
            for f in facts:
                # Keep highest confidence if multiple sources
                current = available_facts.get(f.fact_type, 0.0)
                available_facts[f.fact_type] = max(current, f.confidence)

        gaps = []
        for item in checklist:
            ft = item["fact_type"]
            confidence = available_facts.get(ft, 0.0)
            if confidence < DRE_CONFIDENCE_THRESHOLD:
                gap = EvidenceGap(
                    decision_id="",  # filled by caller
                    fact_type=ft,
                    checklist_weight=item["weight"],
                    current_confidence=confidence,
                    is_compliance_relevant=item.get("compliance", False),
                )
                gap.compute_voi()
                gaps.append(gap)

        # Sort by VoI score descending — highest-value gap first
        gaps.sort(key=lambda g: g.voi_score, reverse=True)
        return gaps

    # ── Relationship Queries ───────────────────────────────────────────────

    def add_relationship(self, from_id: str, to_id: str,
                          rel_type: str, tenant_id: str) -> None:
        """Add a relationship edge between entities."""
        with self._lock:
            self._graph.add_edge(from_id, to_id,
                                  rel_type=rel_type,
                                  tenant_id=tenant_id)

    def get_related_entities(
        self,
        entity_id: str,
        tenant_id: str,
        rel_type: str | None = None,
    ) -> list[str]:
        """Get entities connected to this one."""
        with self._lock:
            related = []
            for _, target, data in self._graph.edges(entity_id, data=True):
                if data.get("tenant_id", tenant_id) != tenant_id:
                    continue
                if rel_type and data.get("rel_type") != rel_type:
                    continue
                if not data.get("node_type") == "fact":  # skip fact nodes
                    related.append(target)
            return related

    # ── Summary / Debug ────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Return a summary of the graph state."""
        with self._lock:
            entity_count = sum(
                1 for _, d in self._graph.nodes(data=True)
                if d.get("node_type") != "fact"
            )
            fact_count = len(self._all_facts)
            return {
                "total_nodes": self._graph.number_of_nodes(),
                "total_edges": self._graph.number_of_edges(),
                "entities": entity_count,
                "facts": fact_count,
            }

    def clear(self) -> None:
        """Clear all data (used in testing)."""
        with self._lock:
            self._graph.clear()
            self._facts.clear()
            self._all_facts.clear()


# Global shared instance
evidence_memory = SharedEvidenceMemory()
