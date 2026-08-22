"""
Veridex NBA Platform — Pipeline Orchestration (§7)

Wires the full decision pipeline end-to-end:
Planner → Evidence Collection (fan-out) → DRE/VoI Loop (cycle) →
Detectors → Bidding Layer (fan-out) → Optimizer → Explanation Engine →
HITL Checkpoints → Outcome Capture

Implements as a procedural pipeline (LangGraph-style semantics without
requiring the dependency — keeps the hackathon build lean while preserving
the graph-based architecture for the walkthrough).

Two distinct HITL pause points:
1. Agent-initiated clarification (Ready-with-caveats only)
2. Terminal accept/edit/reject/"why not X" review
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator, Callable

from backend.models import (
    PipelineState, DecisionRequest, DREStatus, Fact,
    Action, Bid, ClarificationQuestion, HumanDecision,
    Outcome, EntityType, SimilarPastDecision,
    HUMAN_INPUT_CONFIDENCE_CAP,
)
from backend.agents.planner_agent import planner_agent, dynamic_agent_creator
from backend.agents.evidence_agents import AGENT_REGISTRY
from backend.dre import dre, contradiction_detector, missing_info_detector
from backend.bidders.bidders import run_all_bidders
from backend.optimizer import optimizer
from backend.explanation_engine import explanation_engine
from backend.influence_ledger import influence_ledger
from backend.learning_service import learning_service
from backend.memory_graph import evidence_memory
from backend.database import db
from backend.config import MAX_DRE_ITERATIONS
from backend.seed_data import get_all_scenarios
from backend.trace_logger import trace


class DecisionPipeline:
    """
    Full decision pipeline orchestrator.

    Runs the complete Planner → Evidence → DRE/VoI → Bidding → Optimizer →
    Explanation → HITL flow for a decision request.
    """

    def __init__(self):
        self._active_states: dict[str, PipelineState] = {}
        self._progress_callbacks: dict[str, list[Callable]] = {}

    async def run_decision(
        self,
        request: DecisionRequest,
        pre_loaded_facts: list[Fact] | None = None,
    ) -> PipelineState:
        """
        Execute the full decision pipeline for a request.

        Args:
            request: The business decision request
            pre_loaded_facts: Optional pre-loaded facts (from seed data scenarios)

        Returns:
            Final pipeline state with recommendation
        """
        state = PipelineState(decision_request=request)
        self._active_states[request.decision_id] = state

        try:
            # Log the decision
            db.log_decision(
                decision_id=request.decision_id,
                tenant_id=request.tenant_id,
                decision_type=request.decision_type.value,
                primary_entity_id=request.primary_entity_id,
                requested_by=request.requested_by,
            )

            # Stage 1: Planner
            await self._run_planner(state)

            # Stage 2: Evidence Collection
            await self._run_evidence_collection(state, pre_loaded_facts)

            # Stage 3: DRE/VoI Loop
            await self._run_dre_loop(state)

            # Check for BLOCKED status
            if state.dre_status == DREStatus.BLOCKED:
                state.current_stage = "blocked_escalation"
                self._emit_progress(state, "⛔ BLOCKED — escalated to human compliance review")
                db.update_decision_status(request.decision_id, "blocked")
                return state

            # Stage 4: Detectors (can run in parallel with bidding)
            await self._run_detectors(state)

            # Stage 5: Check for agent-initiated clarification (HITL Checkpoint 1)
            if state.dre_status == DREStatus.READY_WITH_CAVEATS and state.evidence_gaps:
                await self._create_clarification(state)

            # Stage 6: Bidding Layer
            await self._run_bidding(state)

            # Stage 7: Optimizer
            await self._run_optimizer(state)

            # Stage 8: Explanation Engine
            await self._run_explanation(state)

            # Stage 9: Ready for HITL Checkpoint 2 (terminal review)
            state.current_stage = "awaiting_human_review"
            state.awaiting_human = True
            self._emit_progress(state, "✅ Recommendation ready for review")
            trace.log(
                decision_id=request.decision_id,
                agent="HITL",
                event="checkpoint_reached",
                detail="awaiting_human_review",
                stage="awaiting_human_review",
            )
            trace.mark_complete(request.decision_id)

            db.update_decision_status(
                request.decision_id, "awaiting_review",
                recommended_action=state.recommended_actions[0].description if state.recommended_actions else "No action"
            )

            # Persist full state to SQLite for cross-restart resilience
            try:
                bids_data = [
                    {
                        "id": b.id,
                        "bidder": b.bidder.value,
                        "score": float(b.score),
                        "rationale": b.rationale,
                        "confidence": float(b.confidence),
                        "is_veto": bool(b.is_veto),
                        "veto_reason": b.veto_reason,
                        "evidence_refs": b.evidence_refs,
                    }
                    for b in state.bids
                ]
                facts_data = [
                    {
                        "id": f.id,
                        "fact_type": f.fact_type,
                        "value": str(f.value),
                        "source": f.source_agent,
                        "confidence": float(f.confidence),
                        "evidence_ref": f.evidence_ref,
                        "entity_id": f.entity_id,
                    }
                    for f in state.facts
                ]
                trace_events = trace.get_trace(request.decision_id)
                
                db.save_decision_state_json(
                    decision_id=request.decision_id,
                    bids_json=json.dumps(bids_data),
                    facts_json=json.dumps(facts_data),
                    progress_json=json.dumps(state.progress_messages),
                    trace_json=json.dumps(trace_events),
                )
            except Exception as ex:
                print(f"[Error] Failed to persist pipeline state JSON: {ex}")

        except Exception as e:
            state.error = str(e)
            state.current_stage = "error"
            self._emit_progress(state, f"❌ Error: {e}")
            raise

        return state

    # ── Pipeline Stages ────────────────────────────────────────────────────

    async def _run_planner(self, state: PipelineState) -> None:
        """Stage 1: Planner Agent — classify and decompose."""
        state.current_stage = "planning"
        self._emit_progress(state, "🧠 Planner Agent: classifying decision and routing agents...")

        plan = planner_agent.plan(state.decision_request)
        state.task_plan = plan

        self._emit_progress(
            state,
            f"📋 Decision classified as {plan.decision_type.value}. "
            f"Routing to {len(plan.assigned_agents)} agents: {', '.join(plan.assigned_agents)}"
        )
        trace.log(
            decision_id=state.decision_request.decision_id,
            agent="PlannerAgent",
            event="classified",
            detail=f"{plan.decision_type.value} — routing to {len(plan.assigned_agents)} agents: {', '.join(plan.assigned_agents)}",
            stage="planning",
        )

    async def _run_evidence_collection(
        self,
        state: PipelineState,
        pre_loaded_facts: list[Fact] | None = None,
    ) -> None:
        """Stage 2: Parallel evidence collection (fan-out)."""
        state.current_stage = "evidence_collection"
        self._emit_progress(state, "🔍 Collecting evidence from all agents in parallel...")

        if pre_loaded_facts:
            # Use pre-loaded facts from seed scenario
            state.facts = pre_loaded_facts
            for fact in pre_loaded_facts:
                evidence_memory.add_fact(fact)
            self._emit_progress(
                state,
                f"📊 Loaded {len(pre_loaded_facts)} evidence facts from {len(set(f.source_agent for f in pre_loaded_facts))} sources"
            )
        else:
            # Run agents
            for agent_name in (state.task_plan.assigned_agents if state.task_plan else []):
                agent = AGENT_REGISTRY.get(agent_name)
                if agent:
                    self._emit_progress(state, f"  → {agent_name}: collecting...")
                    facts = await agent.collect(
                        entity_id=state.decision_request.primary_entity_id,
                        entity_type=state.decision_request.primary_entity_type,
                        tenant_id=state.decision_request.tenant_id,
                        decision_type=state.decision_request.decision_type.value,
                    )
                    state.facts.extend(facts)
                    for fact in facts:
                        evidence_memory.add_fact(fact)
                    self._emit_progress(state, f"  ✓ {agent_name}: {len(facts)} facts collected")
                    trace.log(
                        decision_id=state.decision_request.decision_id,
                        agent=agent_name,
                        event="evidence_returned",
                        detail=f"{len(facts)} facts — types: {', '.join(set(f.fact_type for f in facts))}",
                        stage="evidence_collection",
                    )

    async def _run_dre_loop(self, state: PipelineState) -> None:
        """Stage 3: DRE/VoI loop — the intelligence that targets evidence-gathering."""
        state.current_stage = "dre_evaluation"
        self._emit_progress(state, "⚖️ Decision Readiness Evaluator: checking evidence completeness...")

        for iteration in range(MAX_DRE_ITERATIONS):
            state.dre_iteration = iteration + 1

            # Run DRE
            status, gaps = dre.evaluate(
                facts=state.facts,
                decision_type=state.decision_request.decision_type.value,
                decision_id=state.decision_request.decision_id,
                contradictions=state.contradictions,
            )
            state.dre_status = status
            state.evidence_gaps = gaps

            self._emit_progress(
                state,
                f"  DRE iteration {iteration + 1}: status={status.value}, "
                f"gaps={len(gaps)}"
            )
            trace.log(
                decision_id=state.decision_request.decision_id,
                agent="DRE",
                event="evaluated",
                detail=f"status={status.value}, gaps={len(gaps)}, iteration={iteration + 1}",
                stage="dre_evaluation",
            )

            if status == DREStatus.READY:
                self._emit_progress(state, "  ✅ Decision READY — all evidence sufficient")
                break
            elif status == DREStatus.BLOCKED:
                self._emit_progress(state, "  ⛔ BLOCKED — compliance gap with no caveat-path")
                break
            elif status == DREStatus.READY_WITH_CAVEATS:
                self._emit_progress(
                    state,
                    f"  ⚠️ Ready-with-caveats — {len(gaps)} residual gaps"
                )
                break
            elif status == DREStatus.NOT_READY and gaps:
                # VoI: fetch the highest-value missing fact
                top_gap = gaps[0]
                self._emit_progress(
                    state,
                    f"  🔄 Not Ready — top gap: '{top_gap.fact_type}' "
                    f"(VoI score: {top_gap.voi_score:.2f}). "
                    f"Spinning up dynamic agent..."
                )
                trace.log(
                    decision_id=state.decision_request.decision_id,
                    agent="DynamicAgentCreator",
                    event="agent_spawned",
                    detail=f"fact_type={top_gap.fact_type}, voi_score={top_gap.voi_score:.2f}",
                    stage="dre_evaluation",
                )

                # Dynamic Agent Creator
                new_facts = dynamic_agent_creator.create_agent_for_gap(
                    fact_type=top_gap.fact_type,
                    entity_id=state.decision_request.primary_entity_id,
                    entity_type=state.decision_request.primary_entity_type,
                    tenant_id=state.decision_request.tenant_id,
                    decision_type=state.decision_request.decision_type.value,
                )
                state.facts.extend(new_facts)
                for fact in new_facts:
                    evidence_memory.add_fact(fact)
                self._emit_progress(
                    state,
                    f"  ✓ Dynamic agent found {len(new_facts)} new facts for '{top_gap.fact_type}'"
                )

    async def _run_detectors(self, state: PipelineState) -> None:
        """Stage 4: Contradiction + Missing-Info detectors (continuous)."""
        state.current_stage = "quality_detection"
        self._emit_progress(state, "🔎 Running contradiction and missing-info detectors...")

        # Contradiction detection
        contradictions = contradiction_detector.detect(state.facts)
        state.contradictions = contradictions
        if contradictions:
            self._emit_progress(
                state,
                f"  ⚠️ {len(contradictions)} contradiction(s) found — will be surfaced to reviewer"
            )
            for c in contradictions:
                self._emit_progress(state, f"    → {c['description']}")
            trace.log(
                decision_id=state.decision_request.decision_id,
                agent="ContradictionDetector",
                event="fired",
                detail=f"{len(contradictions)} contradiction(s) found",
                stage="quality_detection",
            )
        else:
            trace.log(
                decision_id=state.decision_request.decision_id,
                agent="ContradictionDetector",
                event="fired",
                detail="No contradictions detected",
                stage="quality_detection",
            )

        # Missing-info detection
        missing = missing_info_detector.detect(
            state.facts,
            state.decision_request.decision_type.value,
        )
        state.missing_info = missing
        if missing:
            self._emit_progress(
                state,
                f"  ℹ️ {len(missing)} missing info item(s) flagged for reviewer"
            )
        trace.log(
            decision_id=state.decision_request.decision_id,
            agent="MissingInfoDetector",
            event="fired",
            detail=f"{len(missing)} missing info item(s)" if missing else "No missing info",
            stage="quality_detection",
        )

    async def _create_clarification(self, state: PipelineState) -> None:
        """
        HITL Checkpoint 1: Agent-initiated clarification (§3.9).

        Only fires on Ready-with-caveats. Surfaces the top-ranked
        unresolved gap as a targeted question to the recruiter.
        """
        if not state.evidence_gaps:
            return

        top_gap = state.evidence_gaps[0]

        # Don't ask about compliance gaps — human input can never resolve those
        if top_gap.is_compliance_relevant:
            return

        # Generate targeted question
        question_map = {
            "competing_offer_signal": f"I couldn't confirm whether the candidate has a competing offer — do you know if they've received or mentioned any other opportunities?",
            "client_satisfaction_signal": f"I have limited data on the client's current satisfaction level — have you had any recent conversations that indicate how they're feeling about our service?",
            "engagement_signal": f"The candidate's engagement signals are unclear — in your recent interactions, did they seem committed to the current role?",
            "redeployment_options": f"I couldn't fully assess redeployment options — are you aware of any other openings that might be a fit?",
            "candidate_response_pattern": f"The candidate's response pattern has changed — do you know of any personal or professional reasons that might explain this?",
        }

        question_text = question_map.get(
            top_gap.fact_type,
            f"I have low confidence on '{top_gap.fact_type}' (currently {top_gap.current_confidence:.0%}). Do you have any additional information on this?"
        )

        state.clarification = ClarificationQuestion(
            decision_id=state.decision_request.decision_id,
            gap=top_gap,
            question_text=question_text,
        )
        self._emit_progress(state, f"❓ Agent question: {question_text}")

    async def process_clarification_answer(
        self,
        decision_id: str,
        answer: str,
    ) -> PipelineState:
        """
        Process human answer to agent-initiated clarification.

        The answer is written as a Fact with source_agent="human_input",
        confidence capped at HUMAN_INPUT_CONFIDENCE_CAP (0.6).

        Human input can NEVER resolve a compliance-relevant gap.
        """
        state = self._active_states.get(decision_id)
        if not state or not state.clarification:
            raise ValueError(f"No active clarification for decision {decision_id}")

        # Write answer as a Fact
        fact = Fact(
            tenant_id=state.decision_request.tenant_id,
            entity_type=state.decision_request.primary_entity_type,
            entity_id=state.decision_request.primary_entity_id,
            fact_type=state.clarification.gap.fact_type,
            value=answer,
            source_agent="human_input",
            confidence=HUMAN_INPUT_CONFIDENCE_CAP,  # Capped, regardless of phrasing
            evidence_ref=f"Human input from {state.decision_request.requested_by}",
        )
        state.facts.append(fact)
        evidence_memory.add_fact(fact)

        state.clarification.answered = True
        state.clarification.answer = answer

        self._emit_progress(
            state,
            f"💬 Human answer recorded (confidence capped at {HUMAN_INPUT_CONFIDENCE_CAP}). Re-evaluating..."
        )

        # Re-run DRE with new fact
        status, gaps = dre.evaluate(
            facts=state.facts,
            decision_type=state.decision_request.decision_type.value,
            decision_id=decision_id,
        )
        state.dre_status = status
        state.evidence_gaps = gaps

        # Continue pipeline from bidding
        await self._run_bidding(state)
        await self._run_optimizer(state)
        await self._run_explanation(state)

        state.current_stage = "awaiting_human_review"
        state.awaiting_human = True

        return state

    async def _run_bidding(self, state: PipelineState) -> None:
        """Stage 6: Multi-Objective Bidding Layer (fan-out)."""
        state.current_stage = "bidding"
        self._emit_progress(state, "🏛️ Running multi-objective bidding layer...")

        bids = run_all_bidders(
            decision_id=state.decision_request.decision_id,
            decision_type=state.decision_request.decision_type.value,
            facts=state.facts,
        )
        state.bids = bids

        # Log bid results
        for bid in bids:
            icon = "🚫" if bid.is_veto else "💰"
            self._emit_progress(
                state,
                f"  {icon} {bid.bidder.value}: score={bid.score:.2f}, "
                f"confidence={bid.confidence:.0%}"
                + (f" VETO: {bid.veto_reason}" if bid.is_veto else "")
            )
            trace.log(
                decision_id=state.decision_request.decision_id,
                agent=bid.bidder.value,
                event="bid_placed",
                detail=f"score={bid.score:.2f}, confidence={bid.confidence:.0%}, veto={bid.is_veto}" + (f", reason={bid.veto_reason}" if bid.is_veto else ""),
                stage="bidding",
            )

        # Track vetoed actions
        state.vetoed_action_ids = [b.proposed_action_id for b in bids if b.is_veto]

    async def _run_optimizer(self, state: PipelineState) -> None:
        """Stage 7: Multi-Objective Optimizer."""
        state.current_stage = "optimization"
        self._emit_progress(state, "⚡ Optimizer: synthesizing recommended action...")

        actions = optimizer.optimize(
            decision_id=state.decision_request.decision_id,
            decision_type=state.decision_request.decision_type.value,
            bids=state.bids,
        )
        state.recommended_actions = actions

        for action in actions:
            if action.action_type.value == "null_no_action":
                state.null_action = True
                self._emit_progress(state, "  ⚪ Optimizer output: NO ACTION RECOMMENDED (below threshold)")
            else:
                self._emit_progress(
                    state,
                    f"  ✅ Recommended action (score: {action.aggregate_score:.2f}): "
                    f"{action.description[:120]}..."
                )
            trace.log(
                decision_id=state.decision_request.decision_id,
                agent="Optimizer",
                event="decision",
                detail=f"action={action.action_type.value}, score={action.aggregate_score:.2f}",
                stage="optimization",
            )

    async def _run_explanation(self, state: PipelineState) -> None:
        """Stage 8: Explanation & Counterfactual Engine."""
        state.current_stage = "explanation"
        self._emit_progress(state, "📝 Generating explanation and counterfactuals...")

        # Get precedent facts
        similar_past = []
        precedent_facts = [f for f in state.facts if f.fact_type == "similar_past_decisions"]
        for pf in precedent_facts:
            # Parse from fact value (simplified)
            similar_past.append(SimilarPastDecision(
                decision_id=pf.evidence_ref.split(": ")[-1] if ": " in pf.evidence_ref else "unknown",
                decision_type=state.decision_request.decision_type,
                similarity_score=pf.confidence,
                action_taken_summary=str(pf.value).split("Action: ")[-1].split(" → ")[0] if "Action: " in str(pf.value) else str(pf.value),
                outcome_summary=str(pf.value).split("Outcome: ")[-1].split(" (")[0] if "Outcome: " in str(pf.value) else "",
            ))

        for action in state.recommended_actions:
            explanation_engine.generate_explanation(
                action=action,
                all_bids=state.bids,
                facts=state.facts,
                similar_past=similar_past,
                contradictions=state.contradictions,
                missing_info=state.missing_info,
            )
        state.similar_past_decisions = similar_past

    # ── Human Decision Processing (HITL Checkpoint 2) ──────────────────────

    async def process_human_decision(
        self,
        decision_id: str,
        human_decision: str,
        edit_description: str = "",
    ) -> dict:
        """
        Process the terminal human decision: accept/edit/reject.

        This is HITL Checkpoint 2 — nothing executes without this.
        """
        state = self._active_states.get(decision_id)
        if not state:
            # Fallback to database check in case of server restart
            db_dec = db._conn.execute(
                "SELECT * FROM decision_log WHERE decision_id = ?",
                (decision_id,)
            ).fetchone()
            
            if not db_dec:
                raise ValueError(f"No active decision: {decision_id}")
            
            # Update decision status in DB
            status_map = {
                "accept": "completed",
                "edit": "completed",
                "reject": "rejected",
            }
            db.update_decision_status(
                decision_id, status_map.get(human_decision, "completed"),
                human_decision=human_decision,
            )
            
            # Record outcome in DB
            outcome = Outcome(
                decision_id=decision_id,
                action_id=None,
                human_decision=HumanDecision(human_decision),
                human_edit_description=edit_description,
                predicted_confidence=0.5,
            )
            db.record_outcome(outcome)
            
            return {
                "decision_id": decision_id,
                "human_decision": human_decision,
                "outcome_recorded": True,
                "learning_updates": ["Database state recovered after restart"],
            }

        state.human_decision = HumanDecision(human_decision)
        state.awaiting_human = False

        action = state.recommended_actions[0] if state.recommended_actions else None
        confidence = action.aggregate_score if action else 0.0

        # Record outcome
        outcome = Outcome(
            decision_id=decision_id,
            action_id=action.action_id if action else None,
            human_decision=HumanDecision(human_decision),
            human_edit_description=edit_description,
            predicted_confidence=confidence,
        )

        # Process through learning service
        result = learning_service.record_outcome(
            outcome=outcome,
            decision_type=state.decision_request.decision_type.value,
            bids=state.bids,
        )

        # Update influence for winning bidders
        if human_decision == "accept" and state.bids:
            for bid in state.bids:
                if not bid.is_veto and bid.score > 0.6:
                    influence_ledger.on_slot_won(bid.bidder.value)

        # Update decision status
        status_map = {
            "accept": "completed",
            "edit": "completed",
            "reject": "rejected",
        }
        db.update_decision_status(
            decision_id, status_map.get(human_decision, "completed"),
            human_decision=human_decision,
        )

        state.current_stage = "completed"
        self._emit_progress(state, f"📌 Human decision: {human_decision.upper()}")

        return {
            "decision_id": decision_id,
            "human_decision": human_decision,
            "outcome_recorded": True,
            "learning_updates": result.get("updates", []),
        }

    def handle_why_not_x(
        self,
        decision_id: str,
        alternative: str,
    ) -> str:
        """
        Handle "Why not X" query — zero extra model calls.

        Reads from already-computed bid state (§3.9).
        Guaranteed-instant UI interaction.
        """
        state = self._active_states.get(decision_id)
        if not state:
            raise ValueError(f"No active decision: {decision_id}")

        action = state.recommended_actions[0] if state.recommended_actions else None
        if not action:
            return "No recommendation to compare against."

        return explanation_engine.handle_why_not_x(
            alternative_description=alternative,
            all_bids=state.bids,
            action=action,
        )

    # ── Scenario Loading ───────────────────────────────────────────────────

    def load_scenario(self, decision_type: str, product_id: str | None = None) -> tuple[DecisionRequest, list[Fact]]:
        """Load a decision scenario. If product_id is given, targets that product and lets live CatalogEvidenceAgent collect facts."""
        scenarios = get_all_scenarios()
        scenario = scenarios.get(decision_type)
        if not scenario:
            raise ValueError(f"No scenario for {decision_type}")
        
        dec_req = scenario["decision"]
        facts = scenario["facts"]

        if product_id:
            import uuid
            dec_req = DecisionRequest(
                decision_id=str(uuid.uuid4()),
                tenant_id=dec_req.tenant_id,
                decision_type=dec_req.decision_type,
                primary_entity_type=dec_req.primary_entity_type,
                primary_entity_id=product_id,
                requested_by=dec_req.requested_by,
                description=f"Catalog Intelligence review for {product_id} ({decision_type})",
                urgency_score=dec_req.urgency_score,
            )
            return dec_req, []

        return dec_req, facts

    # ── State Access ───────────────────────────────────────────────────────

    def get_state(self, decision_id: str) -> PipelineState | None:
        return self._active_states.get(decision_id)

    def get_all_active(self) -> dict[str, PipelineState]:
        return dict(self._active_states)

    # ── Progress Tracking ──────────────────────────────────────────────────

    def _emit_progress(self, state: PipelineState, message: str) -> None:
        """Emit a progress message for streaming UI."""
        timestamped = f"[{datetime.utcnow().strftime('%H:%M:%S')}] {message}"
        state.progress_messages.append(timestamped)

    def get_progress(self, decision_id: str) -> list[str]:
        state = self._active_states.get(decision_id)
        return state.progress_messages if state else []


# Global instance
pipeline = DecisionPipeline()
