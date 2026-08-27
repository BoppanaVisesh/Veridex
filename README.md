# Veridex — AI-Powered Product Catalog Intelligence Platform


<p align="center">
  <img src="sentinel_architecture.jpeg" alt="Veridex System Architecture" width="1000"/>
</p>

<p align="center">
  <em>Figure 1. Veridex Multi-Agent Catalog Intelligence Architecture</em>
</p>

---

## 🎯 Problem Statement

Industrial distributors manage **fragmented product data** across supplier feeds, spec sheets, technical documents, and digital assets. The gap:

| Input (6 columns) | Output Required (252 columns) |
|---|---|
| `Mfg_Part_Num` | Brand Name, Invoice Desc, Mobile Desc, Short Desc, Long Desc |
| `Part_Desc` | DEPT / CLASS / FINE taxonomy (3-level hierarchy) |
| `E1_Brand` | Up to 20 structured attributes (Grit, Voltage, Diameter...) |
| `Unilog_Brand` | Item Features, Series, Material, Color |
| `DIB_Brand` | Compliance flags, certification status |
| `Part_Manuf` | Full Classpath + confidence score |

At scale: thousands of SKUs, multiple suppliers, multiple sales channels — wrong specs cause buyer returns, regulatory fines, and marketplace delisting.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (SPA)                           │
│  8 Pages: Command Center → Run Scenario → Mission Control →     │
│  Investigation → Human Review → Metrics → Catalog → Unilog      │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTP / SSE
┌────────────────────▼────────────────────────────────────────────┐
│                   FASTAPI BACKEND                                │
│                                                                 │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │
│  │ Planner │→ │ Evidence │→ │   DRE    │→ │ Bidding Layer  │  │
│  │  Agent  │  │  Agents  │  │ Evaluator│  │ (6 Bidders)    │  │
│  └─────────┘  └──────────┘  └──────────┘  └───────┬────────┘  │
│                                                    │            │
│  ┌─────────────┐  ┌───────────────┐  ┌────────────▼────────┐  │
│  │  Learning   │← │  Explanation  │← │    Optimizer         │  │
│  │  Service    │  │    Engine     │  │  (Slot Composition)  │  │
│  └─────────────┘  └───────────────┘  └─────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │           Catalog Intelligence Module                      │  │
│  │  Ingestion → Cleaning → Validation → Enrichment → Export  │  │
│  │  Unilog Pipeline: 6 cols → 255-col Delivery Format        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  SQLite Database (decisions, outcomes, products, weights)       │
└─────────────────────────────────────────────────────────────────┘
```

**Stack:** Python 3.13 · FastAPI · SQLite · Vanilla JS SPA · Pandas · Google Gemini Flash (optional)

---

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Set Gemini API key for LLM-enhanced enrichment
# Create .env in root:  GEMINI_API_KEY=your_key_here
# Without key: platform auto-falls back to deterministic rule-based enrichment

# 3. Start the platform
python -m backend.main

# 4. Open the dashboard
http://localhost:8000
```

Server auto-seeds **225 historical outcomes** across all 9 decision types on first boot. No database setup — SQLite is created automatically.

---

## 📄 8 Navigation Pages

| # | Page | Purpose |
|---|---|---|
| **1** | Command Center | KPI tiles, urgency-sorted decision queue, agent health |
| **2** | Run Scenario | Trigger D1–D9 pipelines, animated 8-stage progress |
| **3** | Mission Control | Live stage tracker, agent network SVG, DRE console |
| **4** | Investigation | Radar chart, What-If simulator, evidence timeline, counterfactuals, audit trail |
| **5** | Human Review | Accept / Edit / Reject HITL checkpoint, "Why Not X?" instant query |
| **6** | Platform Metrics | Brier scores, EMA weight drift, influence budgets, business KPIs |
| **7** | Catalog Intelligence | Product grid, enrich/validate, explain-field, CSV/PDF/XLSX upload |
| **8** | Unilog Intelligence | 6→255 col transformation, preview cards, export XLSX/CSV at scale |

---

## 🤖 9 Evidence Agents

| Agent | Catalog Domain Focus |
|---|---|
| Catalog Database Agent | Product status, completeness %, category, age |
| Supplier Ingest Agent | Supplier feed signals, spec conflict notifications |
| Channel Partner Agent | Channel API alignment, taxonomy approval signals |
| Validation Engine Agent | Spec validation status, flagged fields, days since audit |
| Enrichment & Taxonomy Agent | Category value, taxonomy confidence, enrichment yield |
| Marketplace Feed Agent | Comparable products, price benchmarks, feed trends |
| Compliance Registry Agent | ISO/UL/CE cert status — **deterministic, no LLM** |
| Precedent Agent | Similar past decisions (semantic similarity) |
| Catalog Evidence Agent | Full catalog DB lookup for all D-type fact types |

---

## ⚖️ 6 Bidders — Multi-Objective Auction

| Bidder | Weight | Focus | Veto |
|---|---|---|---|
| **Revenue** | 25% | Listing velocity, GMV from unlisted products | No |
| **Risk** | 20% | Spec hallucination, misclassification, RMA returns | No |
| **CustomerSuccess** | 15% | Buyer clarity, fewer disputes, accurate specs | No |
| **Finance** | 15% | Working capital drag, enrichment cost vs manual | No |
| **Compliance** | 15% | ISO/UL/CE certs — **hard veto, never outbid** | **YES** |
| **Ops** | 10% | Pipeline throughput, automation feasibility | No |

> Weights sum to 1.00. EMA learning loop adjusts weights after each outcome. Compliance is exempt from the influence mechanic.

---

## 🗂️ 9 Decision Types — All Industrial Product Data

| ID | Decision | Product | Urgency |
|---|---|---|---|
| **D1** | Listing Readiness Risk | ProPump 5000 — 45% complete, 14 days unlisted | 0.88 |
| **D2** | Category/Channel Placement | Apex Turbine TX-1 — taxonomy + Amazon B2B | 0.65 |
| **D3** | Data Decay Risk | HydroFlow HF-2 — conflicting voltage (110V vs 220V) | 0.85 |
| **D4** | Re-validation Cycle | SolarPower SP-200 — 92 days since audit | 0.60 |
| **D5** | Incomplete Listing Promotion | EcoFlow EF-300 — 35% complete, PDF available | 0.75 |
| **D6** | Source Reliability Health | Global Pump Supplies Feed — 42% validation ratio | 0.78 |
| **D7** | Certification/Compliance Gap | Industrial HD Pump — "Heavy Duty" ≠ UL-778 | 0.95 |
| **D8** | Publish-Confidence Threshold | Titan Valve V-10 — max_pressure_psi at 0.94 confidence | 0.55 |
| **D9** | Catalog Expansion Opportunity | ThermoCool TC-100 — 98% complete, multi-channel ready | 0.50 |

---

## 🔬 Unilog Enrichment Pipeline

```
 Mfg_Part_Num + Part_Desc + E1_Brand + Unilog_Brand + DIB_Brand + Part_Manuf
                                    │
             ┌──────────────────────▼──────────────────────────┐
             │  1. Brand Normalization                          │
             │     Canonical form: "3M", "Milwaukee", "Mirka"  │
             │  2. Manufacturer Normalization                   │
             │     "Milwaukee Electric Tool Corp" → "Milwaukee" │
             │  3. Taxonomy Classification (3-level hierarchy)  │
             │     "FLAP DISC TYPE 27" → Abrasives & Surface    │
             │     Preparation > Cutting & Grinding > Flap Discs│
             │  4. Attribute Extraction (regex, 15 patterns)    │
             │     Grit: 60 | Diameter: 4-1/2 in | Type: 27    │
             │  5. Description Generation (5 variants)         │
             │     Invoice · Mobile · Short · Long · Retail     │
             │  6. Confidence Scoring                          │
             │     0.40 base + classified (+0.25) + attrs       │
             │     (+0.15) + known brand (+0.20) → max 0.95     │
             └──────────────────────┬──────────────────────────┘
                                    │
             ┌──────────────────────▼──────────────────────────┐
             │  255-column Delivery Format output               │
             │  + _confidence score + _needs_review flag        │
             └─────────────────────────────────────────────────┘
```

**Gemini LLM mode** (when `GEMINI_API_KEY` is set): fills empty/low-confidence fields using structured prompt with product context.

---

## 🔒 Key Design Guarantees

### Anti-Hallucination
- Compliance Agent is **100% deterministic** — no LLM, structured registry lookup only
- Compliance Bidder has **hard veto** — cannot be outbid regardless of other scores
- Explanation Engine can only cite `evidence_ref` values **already in state** — no fabrication
- Unilog enrichment is **rule-based by default** — no LLM inference of certification data

### Full Traceability
- Every fact: `source_agent` · `confidence` · `timestamp` · `evidence_ref`
- Every recommendation: bidder scores · counterfactuals · contradictions · precedent · execution log
- Every outcome recorded for learning loop — full audit trail in SQLite

### Human-in-the-Loop
- All decisions require explicit **Accept / Edit / Reject** before execution
- **"Why Not X?"** answers instantly from pre-computed bid state (zero extra LLM calls)
- **What-If simulator** patches numeric facts and recomputes scores without re-running agents

### Continuous Learning
- **EMA** adjusts bidder weights per `(bidder, decision_type)` pair after each outcome
- **Brier Score** calibrates confidence per decision type
- **Influence Budget** tracks win/loss per bidder — prevents single-bidder dominance
- Warm-started with **225 historical outcomes** across D1–D9

---

## 🧪 Test Results

```bash
python test_e2e.py      # Backend E2E — no server needed
python test_pages.py    # API smoke test — server must be running
```

| Test Suite | Result |
|---|---|
| Backend E2E (72 checks) | ✅ 72/72 PASS |
| API smoke test (31 endpoints) | ✅ 31/31 PASS |

---

## 📁 Project Structure

```
veridex/
├── backend/
│   ├── api.py                       # Main FastAPI app (50+ endpoints)
│   ├── main.py                      # Uvicorn entrypoint
│   ├── models.py                    # Pydantic models
│   ├── config.py                    # All tunable parameters
│   ├── database.py                  # SQLite ORM
│   ├── seed_data.py                 # D1–D9 scenarios + 225 historical outcomes
│   ├── dre.py                       # Decision Readiness Evaluator + Detectors
│   ├── optimizer.py                 # Multi-Objective Optimizer
│   ├── explanation_engine.py        # Explanation + Counterfactual Engine
│   ├── learning_service.py          # EMA weight updates + Brier calibration
│   ├── agents/
│   │   ├── evidence_agents.py       # All 8 evidence agent classes
│   │   └── planner_agent.py         # Decision planner
│   ├── bidders/
│   │   └── bidders.py               # 6 bidder classes + run_all_bidders()
│   └── catalog/
│       ├── catalog_api.py           # 15 catalog REST endpoints
│       ├── catalog_models.py        # Product, ProductField models
│       ├── ingestion.py             # CSV/XLSX/PDF/HTML parser
│       ├── cleaning.py              # Raw record normalization
│       ├── catalog_validation.py    # Plausibility + range checks
│       ├── catalog_enrichment.py    # 3-tier enrichment pipeline
│       ├── catalog_explanation.py   # Field-level provenance
│       └── unilog_enrichment.py     # 6→255 col Unilog transformation
├── frontend/
│   ├── index.html                   # SPA shell (8 pages)
│   └── js/
│       ├── app.js                   # Router + nav
│       ├── constants.js             # D-types, agents, bidder metadata
│       ├── helpers.js               # SVG visualizations, shared renderers
│       └── pages/                   # One JS file per page (8 total)
├── test_e2e.py                      # Backend E2E (72 checks)
├── test_pages.py                    # API smoke test (31 endpoints)
├── requirements.txt
└── Unihack_ Sample Dataset - Input.csv
```

---

## 🌐 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Liveness check |
| `/api/scenarios` | GET | All 9 decision scenarios |
| `/api/decisions/run-scenario` | POST | Run pipeline on a scenario |
| `/api/decisions` | GET | List all decisions (urgency-sorted) |
| `/api/decisions/{id}` | GET | Full decision detail + recommendation |
| `/api/decisions/{id}/progress` | GET | Pipeline stage messages |
| `/api/decisions/{id}/stream` | GET | SSE real-time progress |
| `/api/trace/{id}` | GET | Full execution trace |
| `/api/decisions/{id}/respond` | POST | HITL: Accept / Edit / Reject |
| `/api/decisions/{id}/why-not` | POST | "Why not X?" (instant, no LLM) |
| `/api/decisions/{id}/whatif` | POST | What-If fact simulator |
| `/api/metrics` | GET | Platform metrics (influence, Brier, weights) |
| `/api/evaluate` | GET | Business KPIs |
| `/api/catalog/unilog-preview` | GET | Live 6→255 enrichment preview |
| `/api/catalog/unilog-sample-export` | GET | Export enriched dataset (XLSX/CSV) |
| `/api/catalog/products` | GET | Product catalog list |
| `/api/catalog/products/{id}/enrich` | POST | Enrich product fields |
| `/api/catalog/products/{id}/validate` | POST | Validate product fields |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13 · FastAPI · Uvicorn |
| Database | SQLite (auto-created, zero config) |
| AI / LLM | Google Gemini 2.0 Flash (optional) |
| Enrichment | Rule-based pipeline + Gemini fallback |
| Data Processing | Pandas · Regex taxonomy engine |
| Frontend | Vanilla HTML/CSS/JS (no build step) |
| Typography | Google Fonts (Inter) · JetBrains Mono |

---




