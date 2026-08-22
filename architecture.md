# Veridex — Architecture and System Reference Manual

Veridex is an enterprise-grade **Agentic Decision Intelligence Platform** designed for B2B staffing. It automates high-context business decisions—such as matching bench candidates to urgent orders, retaining flight-risk contractors, negotiating bill-rate margins, and cross-selling lines of business—using a structured, multi-agent network governed by mathematical guardrails and persistent feedback loops.

This document details the architectural design, sequential workflows, data schemas, and technical tools that power the Veridex platform.

---

## System Architecture

<p align="center">
  <img src="sentinel_architecture.jpeg" alt="Veridex System Architecture" width="1000"/>
</p>

<p align="center">
  <em>Figure 1. Veridex Multi-Agent Decision Intelligence Architecture</em>
</p>

## 1. Complete Technology Stack & Toolset

Veridex leverages a carefully selected set of lightweight, high-performance, and robust technologies to minimize latency and ensure complete data integrity.

### Backend Infrastructure
*   **Python 3.11**: The core programming runtime, utilizing modern typing, async constructs, and data processing libraries.
*   **FastAPI (v0.115.0)**: Handles asynchronous API endpoints and streams live orchestration progress logs to the frontend via Server-Sent Events (SSE).
*   **Uvicorn (v0.30.0)**: A high-performance ASGI web server implementing the server runtime.
*   **Pydantic (v2.9.0)**: Enforces strict data schemas, validation, and serialization for all data structures (Requests, Actions, Bids, Facts, and Telemetry).
*   **Python-dotenv (v1.0.1)**: Manages local environment variables and API keys.

### Graph & Memory Management
*   **NetworkX (v3.3)**: Powering the **Shared Evidence Memory Graph** ([memory_graph.py](file:///d:/my%20projects/Veridex/backend/memory_graph.py)), representing candidates, clients, and contracts as nodes, with semantic facts and confidence values on the edges.
*   **Sentence-Transformers (`all-MiniLM-L6-v2`)**: Computes local text embeddings to execute semantic search queries, matching candidate resumes and client histories against historical precedents and capability templates.

### Relational Database
*   **SQLite3**: Provides local, disk-backed persistent storage via `sentinel.db`. SQLite holds the entire state of past outcomes, calibrated weights, bidder influence, and audits. It features full recovery across restarts (no loss of learning rate or HITL calibration score).

### Large Language Models (LLM)
*   **Gemini 2.0 Flash / Pro**: Dual-model routing strategy to optimize latency and costs.
    *   **Pro**: Reserved for complex, ambiguous reasoning (Planner, Revenue/Risk Bidding, Explanation generation).
    *   **Flash**: Used for structured extraction and faster execution (Ops/Finance Bidders, Contradiction Detection).

### Frontend Interface
*   **HTML5 & CSS3**: Pure vanilla CSS styles ([styles.css](file:///d:/my%20projects/Veridex/frontend/css/styles.css)) providing a premium, high-fidelity dark/cream dashboard theme, complete with modern typography (Google Fonts *Inter*), micro-animations, glassmorphism, and responsive grids.
*   **Vanilla ES6 JavaScript**: Interactive single-page application split into logic modules:
    *   [app.js](file:///d:/my%20projects/Veridex/frontend/js/app.js): Page routing and global SSE streaming controllers.
    *   [helpers.js](file:///d:/my%20projects/Veridex/frontend/js/helpers.js): Shared helper utilities (e.g. Markdown explanation formatting, SVG orbital node layout, probability tree canvas renderers).
    *   [command.js](file:///d:/my%20projects/Veridex/frontend/js/pages/command.js): Command queue execution metrics and control triggers.
    *   [investigation.js](file:///d:/my%20projects/Veridex/frontend/js/pages/investigation.js): Live orbital network visualization, fact grids, and interactive Checkpoint reviews.
    *   [metrics.js](file:///d:/my%20projects/Veridex/frontend/js/pages/metrics.js): Visual weight trajectories, Brier calibration charts, and database rollback controls.
    *   [scenarios.js](file:///d:/my%20projects/Veridex/frontend/js/pages/scenarios.js): Scenario selection and mock pipeline injector panel.

---

## 2. Multi-Tiered System Architecture

Veridex organizes its capabilities into decoupled, cohesive layers. 

```
                                  [ Recruiter Dashboard ]
                                             │
                                    1. Decision Request
                                             │
┌────────────────────────────────────────────▼────────────────────────────────────────────┐
│ I. ORCHESTRATION & MONITORING LAYER                                                     │
│    [ Planner Agent ] ── routing ──► [ Contradiction & Missing-Info Detectors ]           │
└────────────────────┬───────────────────────────────────▲────────────────────────────────┘
                     │                                   │ updates facts
┌────────────────────▼───────────────────────────────────┴────────────────────────────────┐
│ II. EVIDENCE COLLECTION LAYER                                                           │
│    [ Stateless Agents ] (CRM, Email, Meetings, Candidate Activity, KB, Market, etc.)    │
└────────────────────┬────────────────────────────────────────────────────────────────────┘
                     │ feeds graph data
┌────────────────────▼────────────────────────────────────────────────────────────────────┐
│ III. READINESS & CONTROL LAYER (DRE)                                                    │
│    [ Decision Readiness Evaluator ]                                                      │
│      ├── NOT READY  ──► [ VoI Loop ] ──► [ Dynamic Agent Creator ] ──► (Collect Evidence)│
│      ├── BLOCKED    ──► [ Human Compliance Escalation ] ──► (Bypass Optimizer & Halt)    │
│      └── READY      ──► Proceed to Bidding                                              │
└────────────────────┬────────────────────────────────────────────────────────────────────┘
                     │ evaluated bid parameters
┌────────────────────▼────────────────────────────────────────────────────────────────────┐
│ IV. MULTI-OBJECTIVE BIDDING & OPTIMIZATION LAYER                                        │
│    [ Specialist Bidders ] (CS, Revenue, Finance, Ops, Risk, Compliance Veto)            │
│      └── [ Optimizer ] (Pareto slots, NULL Action generation, influence adjustment)     │
└────────────────────┬────────────────────────────────────────────────────────────────────┘
                     │ composed recommendation
┌────────────────────▼────────────────────────────────────────────────────────────────────┐
│ V. EXPLANATION, HITL, & LEARNING LAYER                                                  │
│    ├── [ Explanation Engine ] (Visual rationales, counterfactuals, past precedents)       │
│    ├── [ Checkpoint 2 Review ] (Approve / Modify / Reject / "Why Not X" instant query)   │
# Veridex — Architecture and System Reference Manual

Veridex is an enterprise-grade **Agentic Decision Intelligence Platform** designed for B2B staffing. It automates high-context business decisions—such as matching bench candidates to urgent orders, retaining flight-risk contractors, negotiating bill-rate margins, and cross-selling lines of business—using a structured, multi-agent network governed by mathematical guardrails and persistent feedback loops.

This document details the architectural design, sequential workflows, data schemas, and technical tools that power the Veridex platform.

---

## System Architecture

<p align="center">
  <img src="sentinel_architecture.jpeg" alt="Veridex System Architecture" width="1000"/>
</p>

<p align="center">
  <em>Figure 1. Veridex Multi-Agent Decision Intelligence Architecture</em>
</p>

## 1. Complete Technology Stack & Toolset

Veridex leverages a carefully selected set of lightweight, high-performance, and robust technologies to minimize latency and ensure complete data integrity.

### Backend Infrastructure
*   **Python 3.11**: The core programming runtime, utilizing modern typing, async constructs, and data processing libraries.
*   **FastAPI (v0.115.0)**: Handles asynchronous API endpoints and streams live orchestration progress logs to the frontend via Server-Sent Events (SSE).
*   **Uvicorn (v0.30.0)**: A high-performance ASGI web server implementing the server runtime.
*   **Pydantic (v2.9.0)**: Enforces strict data schemas, validation, and serialization for all data structures (Requests, Actions, Bids, Facts, and Telemetry).
*   **Python-dotenv (v1.0.1)**: Manages local environment variables and API keys.

### Graph & Memory Management
*   **NetworkX (v3.3)**: Powering the **Shared Evidence Memory Graph** ([memory_graph.py](file:///d:/my%20projects/Veridex/backend/memory_graph.py)), representing candidates, clients, and contracts as nodes, with semantic facts and confidence values on the edges.
*   **Sentence-Transformers (`all-MiniLM-L6-v2`)**: Computes local text embeddings to execute semantic search queries, matching candidate resumes and client histories against historical precedents and capability templates.

### Relational Database
*   **SQLite3**: Provides local, disk-backed persistent storage via `sentinel.db`. SQLite holds the entire state of past outcomes, calibrated weights, bidder influence, and audits. It features full recovery across restarts (no loss of learning rate or HITL calibration score).

### Large Language Models (LLM)
*   **Gemini 2.0 Flash / Pro**: Dual-model routing strategy to optimize latency and costs.
    *   **Pro**: Reserved for complex, ambiguous reasoning (Planner, Revenue/Risk Bidding, Explanation generation).
    *   **Flash**: Used for structured extraction and faster execution (Ops/Finance Bidders, Contradiction Detection).

### Frontend Interface
*   **HTML5 & CSS3**: Pure vanilla CSS styles ([styles.css](file:///d:/my%20projects/Veridex/frontend/css/styles.css)) providing a premium, high-fidelity dark/cream dashboard theme, complete with modern typography (Google Fonts *Inter*), micro-animations, glassmorphism, and responsive grids.
*   **Vanilla ES6 JavaScript**: Interactive single-page application split into logic modules:
    *   [app.js](file:///d:/my%20projects/Veridex/frontend/js/app.js): Page routing and global SSE streaming controllers.
    *   [helpers.js](file:///d:/my%20projects/Veridex/frontend/js/helpers.js): Shared helper utilities (e.g. Markdown explanation formatting, SVG orbital node layout, probability tree canvas renderers).
    *   [command.js](file:///d:/my%20projects/Veridex/frontend/js/pages/command.js): Command queue execution metrics and control triggers.
    *   [investigation.js](file:///d:/my%20projects/Veridex/frontend/js/pages/investigation.js): Live orbital network visualization, fact grids, and interactive Checkpoint reviews.
    *   [metrics.js](file:///d:/my%20projects/Veridex/frontend/js/pages/metrics.js): Visual weight trajectories, Brier calibration charts, and database rollback controls.
    *   [scenarios.js](file:///d:/my%20projects/Veridex/frontend/js/pages/scenarios.js): Scenario selection and mock pipeline injector panel.

---

## 2. Multi-Tiered System Architecture

Veridex organizes its capabilities into decoupled, cohesive layers. 

```
                                  [ Recruiter Dashboard ]
                                             │
                                    1. Decision Request
                                             │
┌────────────────────────────────────────────▼────────────────────────────────────────────┐
│ I. ORCHESTRATION & MONITORING LAYER                                                     │
│    [ Planner Agent ] ── routing ──► [ Contradiction & Missing-Info Detectors ]           │
└────────────────────┬───────────────────────────────────▲────────────────────────────────┘
                     │                                   │ updates facts
┌────────────────────▼───────────────────────────────────┴────────────────────────────────┐
│ II. EVIDENCE COLLECTION LAYER                                                           │
│    [ Stateless Agents ] (CRM, Email, Meetings, Candidate Activity, KB, Market, etc.)    │
└────────────────────┬────────────────────────────────────────────────────────────────────┘
                     │ feeds graph data
┌────────────────────▼────────────────────────────────────────────────────────────────────┐
│ III. READINESS & CONTROL LAYER (DRE)                                                    │
│    [ Decision Readiness Evaluator ]                                                      │
│      ├── NOT READY  ──► [ VoI Loop ] ──► [ Dynamic Agent Creator ] ──► (Collect Evidence)│
│      ├── BLOCKED    ──► [ Human Compliance Escalation ] ──► (Bypass Optimizer & Halt)    │
│      └── READY      ──► Proceed to Bidding                                              │
└────────────────────┬────────────────────────────────────────────────────────────────────┘
                     │ evaluated bid parameters
┌────────────────────▼────────────────────────────────────────────────────────────────────┐
│ IV. MULTI-OBJECTIVE BIDDING & OPTIMIZATION LAYER                                        │
│    [ Specialist Bidders ] (CS, Revenue, Finance, Ops, Risk, Compliance Veto)            │
│      └── [ Optimizer ] (Pareto slots, NULL Action generation, influence adjustment)     │
└────────────────────┬────────────────────────────────────────────────────────────────────┘
                     │ composed recommendation
┌────────────────────▼────────────────────────────────────────────────────────────────────┐
│ V. EXPLANATION, HITL, & LEARNING LAYER                                                  │
│    ├── [ Explanation Engine ] (Visual rationales, counterfactuals, past precedents)       │
│    ├── [ Checkpoint 2 Review ] (Approve / Modify / Reject / "Why Not X" instant query)   │
│    └── [ Learning Service ] (EMA weight adjustment, Brier calibration, influence ledger) │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### I. Orchestration & Monitoring Layer
*   **Planner Agent ([planner_agent.py](file:///d:/my%20projects/Veridex/backend/agents/planner_agent.py))**: Classifies incoming requests against the 9 scenario archetypes (**D1–D9**). It maps the required evidence checklist to active collection agents.
*   **Contradiction Detector ([dre.py](file:///d:/my%20projects/Veridex/backend/dre.py))**: Continually scans evidence facts for logical conflicts (e.g., an Email Sentiment agent reports high contractor satisfaction, while a Meetings Agent reports the contractor is interviewing elsewhere). Upon detection, it caps the confidence of conflicting facts to `min(current_confidence, 0.4)` (ensuring it never raises the confidence of low-confidence facts) to trigger a DRE re-evaluation.
*   **Missing-Info Detector ([dre.py](file:///d:/my%20projects/Veridex/backend/dre.py))**: Identifies missing elements structurally mandated by the decision checklist.

### II. Evidence Collection Layer
*   **Stateless Evidence Agents ([evidence_agents.py](file:///d:/my%20projects/Veridex/backend/agents/evidence_agents.py))**: Query discrete data sources to harvest facts:
    *   *CRM/ATS Agent*: Pulls job orders, bench durations, placements, and contract dates.
    *   *Email Agent*: Harvests contractor communications and sentiment logs.
    *   *Meetings Agent*: Parses QBR and interview transcripts.
    *   *Candidate Activity Agent*: Examines portal logins, assessments, and timesheets.
    *   *Knowledge Base Agent*: Resolves internal rule-books, rate cards, and strategies.
    *   *Market Data Agent*: Matches pricing trends, competitor billing, and talent supply.
    *   *Compliance Registry Agent*: Fetches work visas, backgrounds, and expiry timelines.
    *   *Precedent Agent*: Queries past decision logs using semantic vector search. It enforces a strict **no-match floor** (cosine similarity ≥ 0.81), returning no results rather than forcing a weak match.

### III. Decision Readiness & Control Layer (DRE)
*   **DRE Evaluator ([dre.py](file:///d:/my%20projects/Veridex/backend/dre.py))**: Evaluates graph readiness by matching current facts against checklist weights. Outputs one of four states:
    1.  **READY**: All mandatory evidence exists with high confidence; proceeds directly to bidding.
    2.  **READY_WITH_CAVEATS**: Missing low-importance facts. Triggers Checkpoint 1 (Clarification questions for the recruiter) while continuing.
    3.  **NOT_READY**: Important gaps exist. Initiates the **Value-of-Information (VoI)** cycle: ranks gaps, triggers the **Dynamic Agent Creator** (which instantiates narrow, single-purpose agents templated per gap type, e.g. `DynamicAgent:bench_skill_match`) to fetch the highest-value gap, and loops back.
    4.  **BLOCKED**: A critical compliance fact is missing or negative (confidence = 0.0). HALTS the pipeline, bypasses the optimizer, and escalates to a human reviewer immediately.

### IV. Multi-Objective Bidding & Optimizer Layer
*   **Specialist Bidders ([bidders.py](file:///d:/my%20projects/Veridex/backend/bidders/bidders.py))**: Bid on possible actions based on their individual objective functions:
    *   *Revenue*: Prioritizes invoice value and billing margins.
    *   *Risk*: Minimizes attrition probability and sourcing delays.
    *   *Customer Success*: Measures NPS impacts and client retention.
    *   *Finance*: Focuses on candidate cost-of-bench and margins.
    *   *Ops*: Safeguards recruiter workloads and capacity parameters.
    *   *Compliance*: Checks visa and background clearances. Has **veto power** to eliminate candidate slots entirely.
*   **Optimizer ([optimizer.py](file:///d:/my%20projects/Veridex/backend/optimizer.py))**: Computes the weighted aggregate score of candidate actions using weights adjusted by the **Influence Ledger**.
*   **Influence Ledger ([influence_ledger.py](file:///d:/my%20projects/Veridex/backend/influence_ledger.py))**: Governs the scarcity auction mechanic. Every bidder holds influence (`0.0` to `1.0`). Winning a recommendation costs immediate influence (`0.08`), correct outcomes refund influence (`+0.05`), while incorrect predictions penalize influence further (`-0.05`). A slow replenishment tick (`+0.01` per decision resolved) prevents locked-out states.
*   **Null-Action Threshold**: If no candidate action clears the **`0.38` threshold** in [config.py](file:///d:/my%20projects/Veridex/backend/config.py#L149), the optimizer outputs "No Action Recommended".

### V. Explanation & Learning Feedback Layer
*   **Explanation Engine ([explanation_engine.py](file:///d:/my%20projects/Veridex/backend/explanation_engine.py))**: Generates visual rationales, lists losing options, compiles counterfactual parameters ("What would change this recommendation"), and retrieves past precedents.
*   **Why Not X Challenge Bar**: recruiters can query why a specific alternative option was not recommended. This is resolved with zero-latency by reading the cached bids directly in [explanation_engine.py](file:///d:/my%20projects/Veridex/backend/explanation_engine.py#L232-L268).
*   **Learning Service ([learning_service.py](file:///d:/my%20projects/Veridex/backend/learning_service.py))**: Registers downstream outcome outcomes (e.g. success, failure) and updates weights using Exponential Moving Average (EMA) with a dampened learning rate (`0.05`). It also recalibrates Brier Scores (closer to `0.0` is better) for performance tracking.
*   **Human-Input Confidence Limits**: Any evidence manually keyed in by a human recruiter is strictly capped at `0.6` confidence. Because compliance mandates official third-party validation (e.g. DHS registry lookup), human-input facts can **never** resolve compliance-relevant gaps on their own.

---

## 3. Privacy & Access Control Guardrails

Veridex enforces strict security boundaries directly in the data and query execution layers:
*   **Multi-Tenancy Isolation:** Every fact, decision state, and memory graph node is bound to a specific `tenant_id`. All database queries, vector similarity searches, and agent memory traversals enforce a strict tenant scope; global queries or cross-tenant traversals are completely prohibited.
*   **PII & Access Control:** Sensitive candidate data (such as compensation details, drug tests, background checks, and official work authorization IDs) is role-scoped at the query layer. Only authorized agent pipelines or users with specific roles (e.g. Compliance Auditor) can retrieve the raw text of these variables. PII parameters are automatically redacted or masked in the `decision_log`.

---

## 4. Core Database Schema & Persistence

All outcomes, calibration metrics, and bidding parameters are kept persistent on disk in `sentinel.db`. 

| Table Name | Key Fields | Purpose |
|---|---|---|
| **`decision_log`** | `decision_id` (PK), `tenant_id`, `decision_type`, `status`, `bids_json`, `facts_json`, `progress_json`, `trace_json` | Audits the complete input, execution trace, and final outputs of the agent graph. |
| **`outcomes`** | `decision_id` (PK), `human_decision`, `was_correct`, `predicted_confidence`, `downstream_result` | Logs user approval and downstream execution telemetry to feed the Brier calibrator. |
| **`bidding_weights`** | `(decision_type, bidder)` (Composite PK), `weight`, `updated_at` | Saves active bidding weights after EMA calibration, surviving server restarts. |
| **`weight_snapshots`** | `id` (PK), `decision_type`, `weights` (JSON), `trigger`, `snapshot_at` | Stores a chronological snapshot of weights for potential rollback capabilities. |
| **`influence_ledger`** | `bidder` (PK), `influence`, `total_wins`, `total_correct`, `total_incorrect` | Preserves the active bidding power (influence budget) of each agent team. |
| **`calibration_records`** | `id` (PK), `bidder`, `decision_type`, `sample_size`, `brier_score` | Records historically computed Brier scores to measure HITL prediction quality. |

---

## 5. Sequential Pipeline Flow (Chronological)

The sequential execution of a decision request occurs in 10 sequential phases:

```
[ NLP / Web Request ]
          │
          ▼
1. Planner Classification: Decodes request into scenarios (D1-D9) & generates Task Plan.
          │
          ▼
2. Fan-out Evidence Collection: Stateless agents fetch facts in parallel.
          │
          ▼
3. Shared Graph Population: Facts injected into the NetworkX Shared Evidence Memory Graph.
          │
          ▼
4. DRE Checklist Check: Evaluates completeness. If gap found:
          ├── [VoI Selection] ──► [Dynamic Agent Scan] ──► (Loop back to Step 3)
          └── Proceed if READY.
          │
          ▼
5. Quality Detectors Run: Checks for contradictions and flags missing structural properties.
          │
          ▼
6. Specialists Bid: Active bidders output scores, confidence metrics, and evidence refs.
          │
          ▼
7. Optimizer Aggregation: Evaluates influences, applies veto constraints, and checks score thresholds.
          │
          ▼
8. Explanation Compilation: Generates counterfactuals and pulls semantic vector precedents.
          │
          ▼
9. Human-in-the-Loop Review: Awaiting human review; accepts modifications and "Why Not X" queries.
          │
          ▼
10. Telemetry & EMA updates: Outcomes are resolved, Brier scores updated, weights modified in DB.
```

---

## 6. Main UI Features & Design Aesthetics

Veridex's frontend emphasizes premium, visually rich, and dynamic layouts to elevate user experience:
*   **Orbital Agent Beam network**: Implements an SVG mesh visualization displaying active agent nodes revolving in orbits around the primary decision card. Pulsating neon paths trace the data flow during evidence aggregation.
*   **VoI Animation Loops**: The interface animates dynamic scans when evidence gaps trigger the VoI loop—displaying a dynamically spawned satellite node (e.g. `MarketRateLookup_v1` on the UI mesh) joining the orbit while filling a neon progress bar from 10% to 85%.
*   **Grounded Probability Trees**: Highlights the mathematical expectation of downstream financial outcome projections (`Probability % × bill rate × placement duration`) with readable hover tooltip equations.
*   **Interactive Metrics Visualizer**: Renders beautiful dynamic chart indicators for weight convergence trends, Brier calibration trajectories, and includes a database rollback interface for calibration control.

---

## 7. Key Design Decisions & Rationale

During the architecture and development phases of Veridex, several non-obvious engineering trade-offs were made. These decisions ensure the system remains robust, secure, and mathematically sound under real-world constraints.

### I. "Bidding" vs. "Auction" Nomenclature
*   **Decision:** The decision-making layer was deliberately named the **Bidding Layer** rather than an **Auction Layer**.
*   **Rationale:** In economics, an "auction" implies a competitive, resource-allocation game where independent, self-interested agents bid currency to win a resource. In Veridex, the specialist agents (Revenue, Risk, Customer Success, Finance, Ops) are not adversaries competing in a zero-sum game; they represent cooperating dimensions of a single enterprise's decision utility. Calling it a "bidding" layer emphasizes that agents register their expected utility/impact for various actions, which the optimizer then synthesizes into a multi-objective compromise, avoiding local optimizations that could harm the organization's overall goals.

### II. Technology Rightsizing: NetworkX & SQLite vs. Neo4j & Postgres
*   **Decision:** Veridex uses **NetworkX** for in-memory graph management and **SQLite3** for persistent storage, rather than larger enterprise databases like Neo4j and PostgreSQL.
*   **Rationale:**
    *   **NetworkX vs. Neo4j:** Veridex's Shared Evidence Memory Graph is ephemeral, single-tenant, and evaluated per decision transaction. Using an external graph database like Neo4j would introduce significant network roundtrip latency and deployment complexity for graph operations that NetworkX can resolve in memory in microseconds.
    *   **SQLite vs. PostgreSQL:** SQLite is a serverless, single-file database that provides zero-latency local disk writes. Since the telemetry engine only processes resolved transaction updates sequentially, SQLite provides relational integrity, atomic transactions, and persistence without the deployment, connection pooling, and maintenance overhead of an external Postgres server. It represents the perfect "right-sized" tool matching our architectural constraints.

### III. Score Normalization (Unified Expected Impact)
*   **Decision:** Every bidder must output its score on a unified `0.0` to `1.0` **Expected Impact** scale, rather than raw metrics.
*   **Rationale:** Bidders evaluate completely incompatible units: the Risk bidder measures *attrition probability*, the Customer Success bidder evaluates *relationship sentiment (NPS)*, and the Finance bidder calculates *gross margin percentages*. If bidders submitted raw values, mathematically sound multi-objective aggregation would be impossible. By normalizing all bids to a common scale (`0.0` for worst expected outcome, `1.0` for optimal positive impact), the Optimizer can perform weighted integrations and identify Pareto-optimal recommendations fairly.

### IV. Privacy & Tenancy Isolation
*   **Decision:** Logical tenant isolation is enforced at the database, graph memory, and vector precedent layers.
*   **Rationale:** Veridex is designed for multi-tenant deployment. Both the `evidence_memory` graph and the `sentinel.db` schemas strictly scope all queries using `tenant_id`. The Planner Agent and Precedent Agent are barred from searching or returning precedents from other tenants, ensuring strict data privacy and compliance boundary enforcement.

### V. Contradiction Confidence-Capping Mechanics
*   **Decision:** When a logical contradiction is detected (e.g., contradicting sentiment reports), the confidence score of the conflicting facts is capped at `min(current_confidence, 0.4)`.
*   **Rationale:** Rather than guessing which source is correct, Veridex caps the confidence below the DRE's `0.5` readiness threshold. This automatically invalidates the readiness status, forces the pipeline back into `NOT_READY`, and triggers the Value-of-Information (VoI) loop to dynamically fetch new, clarifying facts to resolve the dispute.

### VI. Human-Input Confidence Capping
*   **Decision:** Any fact entered verbally by a human recruiter is strictly capped at `HUMAN_INPUT_CONFIDENCE_CAP = 0.6` in [models.py](file:///d:/my%20projects/Veridex/backend/models.py#L92).
*   **Rationale:** Humans are prone to cognitive biases and subjective reporting (e.g. a recruiter claiming "the contractor says their work visa is fine"). While human input is valuable context, it should never satisfy compliance checklist items that require official registry verification. Capping human input at `0.6` prevents it from clearing compliance readiness checks on its own, forcing the DRE to wait for official registry scans.
