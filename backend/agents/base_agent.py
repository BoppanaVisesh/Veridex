"""
Veridex NBA Platform — Base Evidence Agent (§3.2)

Abstract base class for all Evidence Agents.
Each agent declares a capability schema — the fact-types it can produce.
This is what the Planner uses for cosine-similarity routing (§3.1).

Every agent follows the same contract:
- Input: entity context (IDs, tenant, decision type)
- Output: list[Fact] with (value, source, confidence, timestamp, evidence_ref)

Prompt-injection hygiene (§11): ingested text from emails, transcripts, etc.
is always treated strictly as data to extract facts from, never as instructions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from backend.models import Fact, EntityType


class BaseEvidenceAgent(ABC):
    """
    Abstract base for all evidence collection agents.

    Subclasses declare:
    - name: unique agent identifier
    - fact_types_produced: what evidence this agent can provide
    - collect(): the actual evidence-gathering logic
    """

    name: str = "base_agent"
    fact_types_produced: list[str] = []
    description: str = ""

    @abstractmethod
    async def collect(
        self,
        entity_id: str,
        entity_type: EntityType,
        tenant_id: str,
        decision_type: str,
        context: dict | None = None,
    ) -> list[Fact]:
        """
        Collect evidence facts for the given entity.

        Args:
            entity_id: The primary entity being evaluated
            entity_type: Type of entity
            tenant_id: Tenant scope
            decision_type: D1-D9 decision type driving this collection
            context: Additional context (e.g., related entity IDs, specific fact types needed)

        Returns:
            List of typed Fact objects to be written to shared memory
        """
        ...

    def can_produce(self, fact_type: str) -> bool:
        """Check if this agent declares capability for a given fact type."""
        return fact_type in self.fact_types_produced

    def capability_text(self) -> str:
        """Return a text description of capabilities for embedding-based matching."""
        return f"{self.name}: produces {', '.join(self.fact_types_produced)}. {self.description}"
