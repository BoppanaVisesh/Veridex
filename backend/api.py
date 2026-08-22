"""
Veridex NBA Platform — FastAPI Application (§7)

REST API endpoints for the decision pipeline:
- Submit new decisions (from pre-built scenarios or custom)
- List/get decisions with urgency-sorted queue
- Human actions: accept/edit/reject, clarification answers, "why not X"
- Metrics: calibration, influence, weight history
- SSE streaming for pipeline progress
- Outcome recording for downstream results
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from backend.graph import pipeline
from backend.models import (
    DecisionRequest, DecisionType, EntityType,
    HumanDecision, Outcome,
)
from backend.database import db
from backend.learning_service import learning_service
from backend.influence_ledger import influence_ledger
from backend.seed_data import TENANT_ID, get_all_scenarios
from backend.config import BASE_BIDDING_WEIGHTS
from backend.trace_logger import trace


# ── App Setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Veridex — Intelligent Next Best Action Platform",
    description="Agentic Decision Intelligence for Product Catalog Operations",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith((".html", ".js", ".css")) or path == "/":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ── Request/Response Models ───────────────────────────────────────────────────

class RunScenarioRequest(BaseModel):
    decision_type: str  # D1-D9
    product_id: Optional[str] = None


class CustomDecisionRequest(BaseModel):
    decision_type: str
    entity_id: str
    entity_type: str = "Product"
    description: str = ""
    requested_by: str = "Catalog_Operations"


class HumanDecisionRequest(BaseModel):
    decision: str  # accept, edit, reject
    edit_description: str = ""


class ClarificationAnswer(BaseModel):
    answer: str


class WhyNotRequest(BaseModel):
    alternative: str


class OutcomeRequest(BaseModel):
    downstream_result: str  # e.g. "filled_in_2_days"
    was_correct: bool


# ── Scenarios Endpoint ────────────────────────────────────────────────────────

@app.get("/api/scenarios")
async def list_scenarios():
    """List all available pre-built decision scenarios."""
    scenarios = get_all_scenarios()
    return {
        dt: {
            "decision_type": dt,
            "description": scenario["decision"].description,
            "primary_entity": scenario["decision"].primary_entity_id,
            "urgency": scenario["decision"].urgency_score,
        }
        for dt, scenario in scenarios.items()
    }


# ── Decision Endpoints ────────────────────────────────────────────────────────

@app.post("/api/decisions/run-scenario")
async def run_scenario(req: RunScenarioRequest):
    """Run a scenario through the full pipeline with live catalog evidence or pre-built defaults.

    Duplicate-prevention: if an unresolved decision already exists for the
    same primary_entity_id + decision_type, return the existing state instead
    of creating a new duplicate.
    """
    try:
        decision_request, facts = pipeline.load_scenario(req.decision_type, product_id=req.product_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # ── Duplicate-prevention check ──────────────────────────────────────
    existing = db.find_active_decision(
        decision_type=decision_request.decision_type.value,
        primary_entity_id=decision_request.primary_entity_id,
    )
    if existing and not req.product_id:
        # Return the existing in-memory state if we still have it
        existing_state = pipeline.get_state(existing["decision_id"])
        if existing_state:
            return _serialize_state(existing_state)
        # If the in-memory state was lost (server restart), reuse the existing ID
        decision_request.decision_id = existing["decision_id"]

    # Run the pipeline (facts=None triggers live CatalogEvidenceAgent collection)
    state = await pipeline.run_decision(decision_request, pre_loaded_facts=facts if facts else None)

    return _serialize_state(state)


@app.post("/api/decisions")
async def create_decision(req: CustomDecisionRequest):
    """Submit a custom decision request."""
    decision_request = DecisionRequest(
        tenant_id=TENANT_ID,
        decision_type=DecisionType(req.decision_type),
        primary_entity_type=EntityType(req.entity_type),
        primary_entity_id=req.entity_id,
        requested_by=req.requested_by,
        description=req.description,
    )

    # ── Duplicate-prevention check ──────────────────────────────────────
    existing = db.find_active_decision(
        decision_type=decision_request.decision_type.value,
        primary_entity_id=decision_request.primary_entity_id,
    )
    if existing:
        existing_state = pipeline.get_state(existing["decision_id"])
        if existing_state:
            return _serialize_state(existing_state)
        # If the in-memory state was lost (server restart), reuse the existing ID
        decision_request.decision_id = existing["decision_id"]

    state = await pipeline.run_decision(decision_request)
    return _serialize_state(state)


@app.get("/api/decisions")
async def list_decisions():
    """List all decisions, sorted by urgency (not FIFO — §3.9)."""
    # Get active pipeline states
    active = pipeline.get_all_active()

    decisions = []
    for dec_id, state in active.items():
        decisions.append({
            "decision_id": dec_id,
            "decision_type": state.decision_request.decision_type.value,
            "description": state.decision_request.description,
            "primary_entity": state.decision_request.primary_entity_id,
            "urgency": state.decision_request.urgency_score,
            "status": state.current_stage,
            "awaiting_human": state.awaiting_human,
            "has_clarification": state.clarification is not None and not state.clarification.answered,
            "created_at": state.decision_request.created_at.isoformat(),
            "human_decision": state.human_decision.value if state.human_decision else None,
        })

    # Sort by urgency (SLA-risk), NOT by creation time
    decisions.sort(key=lambda d: d["urgency"], reverse=True)

    # Add historical decisions from DB
    historical = db.get_all_decisions(limit=50)
    for h in historical:
        if h["decision_id"] not in active:
            decisions.append({
                "decision_id": h["decision_id"],
                "decision_type": h["decision_type"],
                "description": h["recommended_action"] or f"Historical decision {h['decision_id']} for {h['primary_entity_id']}",
                "primary_entity": h["primary_entity_id"],
                "urgency": 0,
                "status": h["status"],
                "awaiting_human": False,
                "has_clarification": False,
                "created_at": h["created_at"],
                "human_decision": h["human_decision"],
            })

    return {"decisions": decisions}


@app.get("/api/decisions/{decision_id}")
async def get_decision(decision_id: str):
    """Get full decision detail with recommendation."""
    state = pipeline.get_state(decision_id)
    if not state:
        # Check if decision exists in db log
        db_dec = db._conn.execute(
            "SELECT * FROM decision_log WHERE decision_id = ?",
            (decision_id,)
        ).fetchone()
        
        if db_dec:
            db_status = db_dec["status"]
            db_human_decision = db_dec["human_decision"]
            
            # Check for recorded outcome
            outcome = db.get_outcome(decision_id)
            
            # Map DB status to awaiting_human
            awaiting_human = False
            if db_status in ("awaiting_review", "pending", "awaiting_human_review"):
                awaiting_human = True
            
            human_dec_val = db_human_decision
            if outcome and outcome.human_decision:
                human_dec_val = outcome.human_decision.value
                awaiting_human = False
            elif db_status in ("completed", "rejected"):
                awaiting_human = False
                
            # Reconstruct bids, facts, progress if saved in DB
            bids = []
            if "bids_json" in db_dec.keys() and db_dec["bids_json"]:
                try:
                    bids = json.loads(db_dec["bids_json"])
                except Exception:
                    pass

            facts = []
            if "facts_json" in db_dec.keys() and db_dec["facts_json"]:
                try:
                    facts = json.loads(db_dec["facts_json"])
                except Exception:
                    pass

            progress = ["Reconstructed from database record."]
            if "progress_json" in db_dec.keys() and db_dec["progress_json"]:
                try:
                    progress = json.loads(db_dec["progress_json"])
                except Exception:
                    pass

            # Reconstruct recommended_actions if we have a recommended action string
            recommended_actions = []
            rec_desc = db_dec["recommended_action"]
            if rec_desc:
                recommended_actions.append({
                    "action_id": f"ACT-{db_dec['decision_type']}-{decision_id[:8]}",
                    "description": rec_desc,
                    "action_type": "accept" if (human_dec_val == "accept") else "reject" if (human_dec_val == "reject") else "edit",
                    "aggregate_score": outcome.predicted_confidence if outcome else 0.85,
                    "explanation": "Reconstructed from database historical record.",
                    "counterfactuals": [],
                    "similar_past_cases": [],
                    "losing_bids": [],
                    "contradictions": [],
                    "missing_info": [],
                })
                
            return {
                "decision_id": db_dec["decision_id"],
                "decision_type": db_dec["decision_type"],
                "description": f"Historical {db_dec['decision_type']} decision request for {db_dec['primary_entity_id']}",
                "primary_entity": db_dec["primary_entity_id"],
                "urgency": 0.0,
                "status": db_status,
                "awaiting_human": awaiting_human,
                "dre_status": "ready" if db_status == "completed" else "blocked" if db_status == "blocked" else "awaiting_review",
                "dre_iterations": 0,
                "evidence_gaps": [],
                "facts_count": len(facts),
                "facts": facts,
                "contradictions": [],
                "missing_info": [],
                "bids": bids,
                "recommended_actions": recommended_actions,
                "null_action": None,
                "clarification": None,
                "progress": progress,
                "error": None,
                "outcome": {
                    "downstream_result": outcome.downstream_result,
                    "was_correct": outcome.was_correct,
                    "human_decision": outcome.human_decision.value if (outcome and outcome.human_decision) else None,
                    "human_edit_description": outcome.human_edit_description,
                } if outcome else None,
            }
        else:
            raise HTTPException(status_code=404, detail="Decision not found")
            
    return _serialize_state(state)


@app.get("/api/decisions/{decision_id}/progress")
async def get_progress(decision_id: str):
    """Get pipeline progress messages."""
    messages = pipeline.get_progress(decision_id)
    return {"messages": messages}


@app.get("/api/decisions/{decision_id}/stream")
async def stream_progress(decision_id: str):
    """SSE endpoint for real-time pipeline progress streaming."""
    async def event_generator():
        last_index = 0
        while True:
            messages = pipeline.get_progress(decision_id)
            if len(messages) > last_index:
                for msg in messages[last_index:]:
                    yield f"data: {json.dumps({'message': msg})}\n\n"
                last_index = len(messages)

            state = pipeline.get_state(decision_id)
            if state and state.current_stage in ("awaiting_human_review", "completed", "error", "blocked_escalation"):
                yield f"data: {json.dumps({'done': True, 'stage': state.current_stage})}\n\n"
                break
            elif not state:
                # Reconstruct completed status from database if active state is lost
                db_dec = db._conn.execute(
                    "SELECT status FROM decision_log WHERE decision_id = ?",
                    (decision_id,)
                ).fetchone()
                if db_dec:
                    yield f"data: {json.dumps({'done': True, 'stage': db_dec['status']})}\n\n"
                    break

            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Trace Endpoints (Live Execution Trace) ─────────────────────────────────

@app.get("/api/trace/{decision_id}")
async def get_trace(decision_id: str):
    """Get full trace for a decision (for replay or late-joining clients)."""
    events = trace.get_trace(decision_id)
    if not events:
        db_dec = db._conn.execute(
            "SELECT trace_json FROM decision_log WHERE decision_id = ?",
            (decision_id,)
        ).fetchone()
        if db_dec and "trace_json" in db_dec.keys() and db_dec["trace_json"]:
            try:
                events = json.loads(db_dec["trace_json"])
            except Exception:
                pass
    return {"decision_id": decision_id, "events": events}


@app.get("/api/trace/{decision_id}/stream")
async def stream_trace(decision_id: str):
    """SSE endpoint for real-time pipeline execution trace streaming."""
    async def trace_generator():
        async for evt in trace.subscribe(decision_id):
            if evt.get("_done"):
                yield f"data: {json.dumps({'done': True})}\n\n"
                break
            yield f"data: {json.dumps(evt)}\n\n"

    return StreamingResponse(
        trace_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Human-in-the-Loop Endpoints ──────────────────────────────────────────────

@app.post("/api/decisions/{decision_id}/respond")
async def respond_to_decision(decision_id: str, req: HumanDecisionRequest):
    """
    HITL Checkpoint 2: Terminal accept/edit/reject.
    Nothing client- or candidate-facing executes without this.
    """
    try:
        result = await pipeline.process_human_decision(
            decision_id=decision_id,
            human_decision=req.decision,
            edit_description=req.edit_description,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/decisions/{decision_id}/clarify")
async def answer_clarification(decision_id: str, req: ClarificationAnswer):
    """
    HITL Checkpoint 1: Answer agent-initiated clarification.
    Human input is capped at 0.6 confidence. Cannot resolve compliance gaps.
    """
    try:
        state = await pipeline.process_clarification_answer(
            decision_id=decision_id,
            answer=req.answer,
        )
        return _serialize_state(state)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/decisions/{decision_id}/why-not")
async def why_not_x(decision_id: str, req: WhyNotRequest):
    """
    "Why not X" query — ZERO extra model calls (§3.9).
    Reads from already-computed bid state. Instant response.
    """
    try:
        response = pipeline.handle_why_not_x(decision_id, req.alternative)
        return {"response": response}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Outcome Endpoint ──────────────────────────────────────────────────────────

@app.post("/api/outcomes/{decision_id}")
async def record_outcome(decision_id: str, req: OutcomeRequest):
    """Record downstream outcome for a decision (for learning loop)."""
    outcome = db.get_outcome(decision_id)
    if not outcome:
        raise HTTPException(status_code=404, detail="No outcome found for this decision")

    # Update with downstream result
    outcome.downstream_result = req.downstream_result
    outcome.was_correct = req.was_correct
    outcome.resolved_at = datetime.utcnow()

    state = pipeline.get_state(decision_id)
    decision_type = state.decision_request.decision_type.value if state else "D1"

    result = learning_service.record_outcome(
        outcome=outcome,
        decision_type=decision_type,
        bids=state.bids if state else None,
    )

    return {
        "outcome_updated": True,
        "downstream_result": req.downstream_result,
        "was_correct": req.was_correct,
        "learning_updates": result.get("updates", []),
    }


# ── Metrics Endpoints ─────────────────────────────────────────────────────────

@app.get("/api/metrics")
async def get_metrics():
    """Get all platform metrics: calibration, influence, weights."""
    return {
        "calibration": learning_service.get_calibration_report(),
        "influence": influence_ledger.get_all_influences(),
        "influence_detailed": db.get_full_influence_ledger(),
        "base_weights": BASE_BIDDING_WEIGHTS,
        "weight_history": learning_service.get_weight_history(),
    }


@app.get("/api/metrics/influence")
async def get_influence():
    """Get current influence values for all bidders."""
    return influence_ledger.get_all_influences()


@app.get("/api/metrics/calibration")
async def get_calibration():
    """Get calibration report (Brier scores)."""
    return learning_service.get_calibration_report()


@app.get("/api/metrics/weights")
async def get_weight_history(decision_type: Optional[str] = None):
    """Get weight snapshot history."""
    return learning_service.get_weight_history(decision_type)


# ── Evaluation Endpoint ───────────────────────────────────────────────────────

@app.get("/api/evaluate")
async def run_platform_evaluation(run: bool = False):
    """
    Run full platform evaluation: pipeline quality + business KPIs (§13).
    Returns per-scenario decision metrics + §2.4 business outcome metrics
    computed from the seeded historical outcomes database.
    """
    from backend.evaluation import run_evaluation, compute_business_outcome_metrics
    if run:
        report = await run_evaluation()
    else:
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "platform": "Veridex NBA Platform v1.0",
            "summary": {
                "total_scenarios": 0,
                "successful_runs": 0,
                "blocked_correctly": 0,
                "avg_aggregate_score": 0,
                "min_aggregate_score": 0,
                "max_aggregate_score": 0,
                "avg_facts_per_decision": 0,
                "avg_dre_iterations": 0,
                "explanation_coverage": "0/0",
                "total_counterfactuals": 0,
                "total_contradictions": 0,
            },
            "results": {},
        }
    report["business_kpis"] = compute_business_outcome_metrics()
    return report




# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "platform": "Veridex NBA Platform",
        "version": "1.0.0",
        "memory_graph": str(pipeline._active_states.keys()),
    }


# ── Serialization Helpers ─────────────────────────────────────────────────────

def _serialize_state(state) -> dict:
    """Serialize PipelineState for API response."""
    outcome = db.get_outcome(state.decision_request.decision_id)
    result = {
        "decision_id": state.decision_request.decision_id,
        "decision_type": state.decision_request.decision_type.value,
        "description": state.decision_request.description,
        "primary_entity": state.decision_request.primary_entity_id,
        "urgency": state.decision_request.urgency_score,
        "status": state.current_stage,
        "awaiting_human": state.awaiting_human,
        "outcome": {
            "downstream_result": outcome.downstream_result,
            "was_correct": outcome.was_correct,
            "human_decision": outcome.human_decision.value if (outcome and outcome.human_decision) else None,
            "human_edit_description": outcome.human_edit_description,
        } if outcome else None,

        # DRE
        "dre_status": state.dre_status.value,
        "dre_iterations": state.dre_iteration,
        "evidence_gaps": [
            {
                "fact_type": g.fact_type,
                "voi_score": round(g.voi_score, 3),
                "current_confidence": g.current_confidence,
                "is_compliance": g.is_compliance_relevant,
            }
            for g in state.evidence_gaps
        ],

        # Evidence
        "facts_count": len(state.facts),
        "facts": [
            {
                "id": f.id,
                "fact_type": f.fact_type,
                "value": str(f.value)[:300],
                "source": f.source_agent,
                "confidence": f.confidence,
                "evidence_ref": f.evidence_ref,
                "entity_id": f.entity_id,
                "timestamp": f.timestamp.isoformat() if hasattr(f, 'timestamp') and f.timestamp else None,
            }
            for f in state.facts
        ],

        # Quality
        "contradictions": state.contradictions,
        "missing_info": state.missing_info,

        # Bids
        "bids": [
            {
                "id": b.id,
                "bidder": b.bidder.value,
                "score": round(b.score, 3),
                "rationale": b.rationale,
                "confidence": round(b.confidence, 3),
                "is_veto": b.is_veto,
                "veto_reason": b.veto_reason,
                "evidence_refs": b.evidence_refs,
            }
            for b in state.bids
        ],

        # Recommendation
        "recommended_actions": [
            {
                "action_id": a.action_id,
                "description": a.description,
                "action_type": a.action_type.value,
                "aggregate_score": a.aggregate_score,
                "explanation": a.explanation,
                "counterfactuals": a.counterfactuals,
                "similar_past_cases": [
                    {
                        "decision_id": sp.decision_id,
                        "similarity_score": sp.similarity_score,
                        "action_taken": sp.action_taken_summary,
                        "outcome": sp.outcome_summary,
                    }
                    for sp in a.similar_past_cases
                ],
                "losing_bids": a.losing_bids_summary,
                "contradictions": a.contradictions,
                "missing_info": a.missing_info,
            }
            for a in state.recommended_actions
        ],
        "null_action": state.null_action,

        # Clarification (HITL Checkpoint 1)
        "clarification": {
            "question": state.clarification.question_text,
            "gap_type": state.clarification.gap.fact_type,
            "answered": state.clarification.answered,
            "answer": state.clarification.answer,
        } if state.clarification else None,

        # Progress
        "progress": state.progress_messages,

        # Error
        "error": state.error,
    }

    return result


# ── What-If Simulator ─────────────────────────────────────────────────────────

class WhatIfRequest(BaseModel):
    overrides: dict


@app.post("/api/decisions/{decision_id}/whatif")
async def whatif_simulation(decision_id: str, req: WhatIfRequest):
    """
    What-If simulator: patch numeric fact values and recompute bid scores.

    Re-uses the pre-computed bid objects in memory — no agent re-invocation.
    Each bidder score is linearly nudged based on how the overrides change
    fact values relative to their original values.
    """
    state = pipeline.get_state(decision_id)
    if not state:
        raise HTTPException(status_code=404, detail="Decision not found or expired")

    original_actions = state.recommended_actions or []
    original_score   = original_actions[0].aggregate_score if original_actions else 0.0
    original_bids    = state.bids or []

    if not original_bids:
        raise HTTPException(status_code=400, detail="No bids computed yet for this decision")

    # Build a fact lookup {fact_type: numeric_value}
    fact_values: dict[str, float] = {}
    for f in (state.facts or []):
        raw = str(f.value or "").replace(",", "").replace("%", "").strip()
        try:
            fact_values[f.fact_type] = float(raw)
        except ValueError:
            pass

    # Compute override deltas as relative changes (-1 to +1)
    deltas: dict[str, float] = {}
    for key, new_val in req.overrides.items():
        try:
            nv = float(new_val)
            ov = fact_values.get(key)
            if ov is not None and abs(ov) > 1e-9:
                deltas[key] = (nv - ov) / max(abs(ov), 1e-9)
            else:
                deltas[key] = 0.0
        except (TypeError, ValueError):
            pass

    # Each bidder score nudged proportionally — cap between 0 and 1
    nudge_factor = 0.08   # max 8% change per override unit
    total_nudge  = sum(deltas.values()) * nudge_factor / max(len(deltas), 1)

    patched_bids = []
    for b in original_bids:
        base   = b.score or 0.0
        # Different bidders have different sensitivities
        sensitivity = {
            "Revenue": 1.2, "Risk": 0.9, "CustomerSuccess": 1.1,
            "Finance": 1.0, "Ops": 0.8,  "Compliance": 0.3,
        }.get(b.bidder, 1.0)
        patched_score = max(0.0, min(1.0, base + total_nudge * sensitivity))
        patched_bids.append({
            "bidder":         b.bidder,
            "original_score": base,
            "patched_score":  round(patched_score, 4),
            "delta":          round(patched_score - base, 4),
        })

    # Re-aggregate using same weight logic
    from backend.config import BASE_BIDDING_WEIGHTS
    weights = BASE_BIDDING_WEIGHTS.get(state.decision_request.decision_type, {})
    patched_aggregate = sum(
        pb["patched_score"] * weights.get(pb["bidder"], 0.15)
        for pb in patched_bids
        if not any(b.is_veto and b.bidder == pb["bidder"] for b in original_bids)
    )
    patched_aggregate = round(min(1.0, patched_aggregate), 4)

    recommendation_flipped = (
        (original_score > 0.5) != (patched_aggregate > 0.5)
    )

    return {
        "decision_id": decision_id,
        "overrides":   req.overrides,
        "original": {"aggregate_score": round(original_score, 4)},
        "patched":  {"aggregate_score": patched_aggregate},
        "score_delta":            round(patched_aggregate - original_score, 4),
        "recommendation_flipped": recommendation_flipped,
        "bid_deltas":             patched_bids,
    }


# ── Admin Endpoints ───────────────────────────────────────────────────────────

@app.post("/api/admin/reset")
async def admin_reset():
    """Delete ALL decision_log and outcome records. Full clean slate."""
    decisions_deleted = db.delete_all_decisions()
    outcomes_deleted = db.delete_all_outcomes()

    # Clear in-memory pipeline states
    pipeline._active_states.clear()

    return {
        "decisions_deleted": decisions_deleted,
        "outcomes_deleted": outcomes_deleted,
        "status": "reset_complete",
    }
