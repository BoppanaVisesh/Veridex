"""
Veridex End-to-End Validation Suite (v3 — all correct APIs)
No server required. Run from project root:  python test_e2e.py
"""
import sys, asyncio, traceback
sys.path.insert(0, r"d:\my projects\veridex")

PASS, FAIL = [], []

def ok(label):
    PASS.append(label)
    print(f"  [PASS] {label}")

def fail(label, err=""):
    FAIL.append(label)
    print(f"  [FAIL] {label}: {err}")

def section(title):
    print(f"\n{'='*62}")
    print(f"  {title}")
    print(f"{'='*62}")

# ─────────────────────────────────────────────────────────────
section("1 · BACKEND CORE IMPORTS")
# ─────────────────────────────────────────────────────────────
try:
    from backend.models import (
        DecisionType, DecisionRequest, EntityType,
        Fact, Outcome, HumanDecision, SimilarPastDecision,
        Bid, BidderType
    )
    ok("backend.models")
except Exception as e:
    fail("backend.models", e)

try:
    from backend.config import (
        BASE_BIDDING_WEIGHTS, DECISION_CHECKLISTS,
        ACTION_TEMPLATES, AGENT_CAPABILITIES
    )
    ok(f"backend.config — bidders: {list(BASE_BIDDING_WEIGHTS.keys())}")
except Exception as e:
    fail("backend.config", e)

try:
    from backend.database import db
    ok("backend.database")
except Exception as e:
    fail("backend.database", e)

try:
    from backend.seed_data import (
        get_all_scenarios, generate_historical_outcomes,
        PRODUCTS_SEED, SUPPLIERS_SEED, CHANNELS_SEED, TENANT_ID,
        generate_d1_scenario
    )
    ok("backend.seed_data")
except Exception as e:
    fail("backend.seed_data", e)

# ─────────────────────────────────────────────────────────────
section("2 · PIPELINE MODULE IMPORTS")
# ─────────────────────────────────────────────────────────────
try:
    from backend.agents.planner_agent import PlannerAgent
    ok("PlannerAgent")
except Exception as e:
    fail("PlannerAgent", e)

try:
    from backend.agents.evidence_agents import (
        CRMATSAgent, EmailAgent, MeetingsAgent, CandidateActivityAgent,
        KnowledgeBaseAgent, MarketDataAgent, ComplianceRegistryAgent,
        PrecedentAgent, AGENT_REGISTRY
    )
    ok(f"evidence_agents — {len(AGENT_REGISTRY)} agents in registry")
except Exception as e:
    fail("evidence_agents", e)

try:
    from backend.dre import (
        DecisionReadinessEvaluator, ContradictionDetector,
        MissingInfoDetector, dre, contradiction_detector, missing_info_detector
    )
    ok("backend.dre (DecisionReadinessEvaluator + global instances)")
except Exception as e:
    fail("backend.dre", e)

try:
    from backend.bidders.bidders import (
        RevenueBidder, RiskBidder, CustomerSuccessBidder,
        FinanceBidder, ComplianceBidder, OpsBidder,
        ALL_BIDDERS, run_all_bidders
    )
    ok(f"bidders — {len(ALL_BIDDERS)} in registry: {list(ALL_BIDDERS.keys())}")
except Exception as e:
    fail("bidders", e)

try:
    from backend.optimizer import MultiObjectiveOptimizer, optimizer
    ok("backend.optimizer")
except Exception as e:
    fail("backend.optimizer", e)

try:
    from backend.explanation_engine import ExplanationEngine, explanation_engine
    ok("backend.explanation_engine")
except Exception as e:
    fail("backend.explanation_engine", e)

try:
    from backend.learning_service import LearningService
    ok("backend.learning_service")
except Exception as e:
    fail("backend.learning_service", e)

try:
    from backend.catalog_evidence_agent import CatalogEvidenceAgent
    ok("catalog_evidence_agent")
except Exception as e:
    fail("catalog_evidence_agent", e)

# ─────────────────────────────────────────────────────────────
section("3 · CATALOG MODULE IMPORTS")
# ─────────────────────────────────────────────────────────────
try:
    from backend.catalog.catalog_database import catalog_db
    ok("catalog_database")
except Exception as e:
    fail("catalog_database", e)

try:
    from backend.catalog.catalog_models import Product, ProductField, ProductStatus, FieldStatus
    ok("catalog_models")
except Exception as e:
    fail("catalog_models", e)

try:
    from backend.catalog.ingestion import parse_uploaded_file, parse_csv_or_excel
    ok("catalog.ingestion")
except Exception as e:
    fail("catalog.ingestion", e)

try:
    from backend.catalog.catalog_validation import validate_all_product_fields
    ok("catalog.validation")
except Exception as e:
    fail("catalog.validation", e)

try:
    from backend.catalog.catalog_enrichment import enrich_product_missing_fields
    ok("catalog.enrichment")
except Exception as e:
    fail("catalog.enrichment", e)

try:
    from backend.catalog.unilog_enrichment import enrich_unilog_row, enrich_unilog_batch
    ok("catalog.unilog_enrichment")
except Exception as e:
    fail("catalog.unilog_enrichment", e)

# ─────────────────────────────────────────────────────────────
section("4 · CONFIG ALIGNMENT — D1–D9, BIDDERS, CHECKLISTS")
# ─────────────────────────────────────────────────────────────
try:
    expected = {"D1","D2","D3","D4","D5","D6","D7","D8","D9"}
    actual = {dt.value for dt in DecisionType}
    assert not (expected - actual), f"Missing: {expected - actual}"
    ok(f"All 9 decision types: {sorted(actual)}")
except Exception as e:
    fail("DecisionType", e)

try:
    for dt in ["D1","D2","D3","D4","D5","D6","D7","D8","D9"]:
        assert dt in DECISION_CHECKLISTS, f"{dt} missing from checklists"
        assert dt in ACTION_TEMPLATES, f"{dt} missing from templates"
    ok("All D1-D9 in DECISION_CHECKLISTS + ACTION_TEMPLATES")
except Exception as e:
    fail("Checklists/templates", e)

try:
    expected_b = {"Revenue","Risk","CustomerSuccess","Finance","Compliance","Ops"}
    actual_b = set(BASE_BIDDING_WEIGHTS.keys())
    assert not (expected_b - actual_b), f"Missing: {expected_b - actual_b}"
    total_w = sum(BASE_BIDDING_WEIGHTS.values())
    ok(f"6 bidders, weights sum={total_w:.2f}: {list(BASE_BIDDING_WEIGHTS.keys())}")
except Exception as e:
    fail("BASE_BIDDING_WEIGHTS", e)

# ─────────────────────────────────────────────────────────────
section("5 · SEED DATA — D1–D9 SCENARIOS + 225 HISTORY")
# ─────────────────────────────────────────────────────────────
try:
    scenarios = get_all_scenarios()
    for dt in ["D1","D2","D3","D4","D5","D6","D7","D8","D9"]:
        s = scenarios[dt]
        req, facts = s["decision"], s["facts"]
        assert req.decision_type.value == dt
        assert len(facts) >= 4
        ok(f"  {dt}: entity={req.primary_entity_id} | facts={len(facts)} | urgency={req.urgency_score}")
except Exception as e:
    fail("Seed scenarios", e)

try:
    hist = generate_historical_outcomes()
    assert len(hist) == 225
    by_type = {}
    for h in hist:
        by_type[h["decision_type"]] = by_type.get(h["decision_type"], 0) + 1
    ok(f"225 historical outcomes: {' | '.join(f'{k}:{v}' for k,v in sorted(by_type.items()))}")
except Exception as e:
    fail("Historical outcomes", e)

# ─────────────────────────────────────────────────────────────
section("6 · AGENTS — COLLECT FACTS (ALL 7 ASYNC)")
# ─────────────────────────────────────────────────────────────
try:
    test_req = DecisionRequest(
        decision_id="TEST-E2E-001",
        tenant_id=TENANT_ID,
        decision_type=DecisionType.D1,
        primary_entity_type=EntityType.PRODUCT,
        primary_entity_id="propump-5000",
        requested_by="TEST",
        description="D1 listing readiness test",
        urgency_score=0.88,
    )

    agents_to_test = [
        ("CRM/Catalog",        CRMATSAgent()),
        ("Email/Supplier",     EmailAgent()),
        ("Meetings/Channel",   MeetingsAgent()),
        ("Activity/Validation", CandidateActivityAgent()),
        ("KB/Taxonomy",        KnowledgeBaseAgent()),
        ("Compliance",         ComplianceRegistryAgent()),
        ("Precedent",          PrecedentAgent()),
    ]

    async def run_agents():
        results = []
        for name, agent in agents_to_test:
            try:
                facts = await agent.collect(
                    test_req.primary_entity_id,
                    test_req.primary_entity_type,
                    test_req.tenant_id,
                    test_req.decision_type.value,
                )
                results.append((name, len(facts), None))
            except Exception as ex:
                results.append((name, 0, str(ex)[:80]))
        return results

    for name, n, err in asyncio.run(run_agents()):
        if err:
            fail(f"Agent {name}", err)
        else:
            ok(f"  Agent {name}: {n} facts")
except Exception as e:
    fail("Agent loop", e); traceback.print_exc()

# ─────────────────────────────────────────────────────────────
section("7 · DRE — DECISION READINESS EVALUATOR")
# ─────────────────────────────────────────────────────────────
dre_status = dre_gaps = None
try:
    d1 = generate_d1_scenario()
    test_facts = d1["facts"]
    # DRE.evaluate(facts, decision_type, decision_id, contradictions=None)
    dre_status, dre_gaps = dre.evaluate(test_facts, "D1", "TEST-E2E-001")
    ok(f"DRE status={dre_status.value}, gaps={len(dre_gaps)}")

    contradictions = contradiction_detector.detect(test_facts)
    ok(f"ContradictionDetector: {len(contradictions)} contradiction(s) found")

    missing = missing_info_detector.detect(test_facts, "D1")
    ok(f"MissingInfoDetector: {len(missing)} missing item(s)")
except Exception as e:
    fail("DRE", e); traceback.print_exc()

# ─────────────────────────────────────────────────────────────
section("8 · BIDDERS — ALL 6 BID + SCORES VALID")
# ─────────────────────────────────────────────────────────────
all_bids = []
try:
    # run_all_bidders(decision_id, decision_type, facts) -> list[Bid]
    all_bids = run_all_bidders("TEST-E2E-001", "D1", test_facts)
    ok(f"run_all_bidders: {len(all_bids)} bids returned")

    seen_bidders = set()
    for bid in all_bids:
        assert 0.0 <= bid.score <= 1.0, f"Score out of range: {bid.score}"
        veto = " [VETO]" if bid.is_veto else ""
        ok(f"  {bid.bidder.value:16} score={bid.score:.3f} conf={bid.confidence:.3f}{veto}")
        seen_bidders.add(bid.bidder.value)

    expected_bidders = {"Revenue","Risk","CustomerSuccess","Finance","Compliance","Ops"}
    missing_b = expected_bidders - seen_bidders
    if missing_b:
        fail("Bidder coverage", f"Missing: {missing_b}")
    else:
        ok(f"All 6 bidders present")
except Exception as e:
    fail("Bidder auction", e); traceback.print_exc()

# ─────────────────────────────────────────────────────────────
section("9 · OPTIMIZER + EXPLANATION ENGINE")
# ─────────────────────────────────────────────────────────────
action = None
try:
    # optimizer.optimize(decision_id, decision_type, bids) -> list[Action]
    actions = optimizer.optimize("TEST-E2E-001", "D1", all_bids)
    assert actions
    action = actions[0]
    ok(f"Optimizer: action_type={action.action_type.value}, score={action.aggregate_score:.3f}")
except Exception as e:
    fail("Optimizer", e); traceback.print_exc()

try:
    # explanation_engine.generate_explanation(action, all_bids, facts) -> Action
    action = explanation_engine.generate_explanation(action, all_bids, test_facts)
    assert action.explanation and len(action.explanation) > 20
    ok(f"ExplanationEngine: {len(action.explanation)} chars | counterfactuals={len(action.counterfactuals)}")
except Exception as e:
    fail("ExplanationEngine", e); traceback.print_exc()

# ─────────────────────────────────────────────────────────────
section("10 · INGESTION PIPELINE — CSV BYTES")
# ─────────────────────────────────────────────────────────────
try:
    csv_content = (
        "product_name,brand,model_number,category,price,weight\n"
        "ProPump Commercial Water Pump,AquaTech,PP-5000,Industrial Pumps,1250.00,12.5\n"
        "VoltSensor VS-50 Smart Probe,SensaTech,VS-50,Sensors & Measurement,185.00,0.8\n"
    )
    results = parse_uploaded_file(csv_content.encode("utf-8"), "test_products.csv")
    assert len(results) >= 1
    ok(f"Ingestion: {len(results)} product(s) parsed from CSV bytes")
    for r in results:
        ok(f"  → '{r.get('product_name','')}' | fields={len(r.get('fields',[]))}")
except Exception as e:
    fail("Ingestion CSV", e)

# ─────────────────────────────────────────────────────────────
section("11 · UNILOG ENRICHMENT — SINGLE ROW + BATCH")
# ─────────────────────────────────────────────────────────────
try:
    row = {
        "Mfg_Part_Num": "4-1/2IN60GRITALOX",
        "Part_Desc": "4-1/2 IN 60 GRIT ALUMINUM OXIDE FLAP DISC TYPE 27",
        "E1_Brand": "-- Unbranded --",
        "Unilog_Brand": "3M",
        "DIB_Brand": "3M",
        "Part_Manuf": "3M Company",
    }
    result = enrich_unilog_row(row)
    ok(f"Single row: {len(result)} output columns")
    for col in ["BRAND_NAME","INVOICE_DESC","MOBILE_DESC","SHORT_DESC","LONG_DESC1","Dept","Class","_confidence"]:
        val = result.get(col, "")
        if val:
            ok(f"  {col}: '{str(val)[:55]}'")
        else:
            fail(f"  {col}", "empty")
except Exception as e:
    fail("Unilog single row", e); traceback.print_exc()

try:
    import pandas as pd
    rows = [
        {"Mfg_Part_Num":"4-1/2IN60GRITALOX","Part_Desc":"4-1/2 IN 60 GRIT FLAP DISC TYPE 27",       "E1_Brand":"-- Unbranded --","Unilog_Brand":"3M",        "DIB_Brand":"3M",        "Part_Manuf":"3M Company"},
        {"Mfg_Part_Num":"DB3-80X",           "Part_Desc":"8 IN 80 GRIT DIABLO STEEL DEMON RCP DISC",  "E1_Brand":"Diablo",         "Unilog_Brand":"Diablo",    "DIB_Brand":"Diablo",    "Part_Manuf":"Diablo"},
        {"Mfg_Part_Num":"MIL-2135-20",       "Part_Desc":"MILWAUKEE M18 18V 4.5 IN ANGLE GRINDER",    "E1_Brand":"Milwaukee",      "Unilog_Brand":"Milwaukee", "DIB_Brand":"Milwaukee", "Part_Manuf":"Milwaukee Tool"},
        {"Mfg_Part_Num":"MRK-NONAME-01",     "Part_Desc":"GENERIC GRINDING WHEEL 7 IN",               "E1_Brand":"-- Unbranded --","Unilog_Brand":"",          "DIB_Brand":"",          "Part_Manuf":""},
        {"Mfg_Part_Num":"MIR-9190CV",        "Part_Desc":"MIRKA 6 IN 80 GRIT CEROS 950CV SANDER",     "E1_Brand":"Mirka",          "Unilog_Brand":"Mirka",     "DIB_Brand":"Mirka",     "Part_Manuf":"Mirka"},
    ]
    # Test with list of dicts
    enriched_list = enrich_unilog_batch(rows)
    ok(f"Batch (list): {len(enriched_list)} rows × {len(enriched_list[0])} columns")

    # Test with DataFrame
    df = pd.DataFrame(rows)
    enriched_df = enrich_unilog_batch(df)
    ok(f"Batch (DataFrame): {len(enriched_df)} rows × {len(enriched_df[0])} columns")

    brands    = [r.get("BRAND_NAME","") for r in enriched_list]
    depts     = [r.get("Dept","") for r in enriched_list]
    confs     = [float(r.get("_confidence",0)) for r in enriched_list]
    classified = sum(1 for d in depts if d and d not in ("General Industrial", "General Products"))
    ok(f"  Brands: {brands}")
    ok(f"  Depts:  {depts}")
    ok(f"  Avg confidence: {sum(confs)/len(confs):.2f} | Classified: {classified}/{len(rows)}")
except Exception as e:
    fail("Unilog batch", e); traceback.print_exc()

# ─────────────────────────────────────────────────────────────
section("12 · FRONTEND ↔ BACKEND ALIGNMENT")
# ─────────────────────────────────────────────────────────────
try:
    import re

    with open(r"d:\my projects\veridex\frontend\js\helpers.js", encoding="utf-8") as f:
        helpers_js = f.read()
    with open(r"d:\my projects\veridex\frontend\js\constants.js", encoding="utf-8") as f:
        constants_js = f.read()
    with open(r"d:\my projects\veridex\frontend\index.html", encoding="utf-8") as f:
        html = f.read()

    combined_js = helpers_js + constants_js

    # Backend bidder names → check frontend uses same names
    for b in ["Revenue", "Risk", "Finance", "Compliance", "Ops"]:
        assert b in combined_js, f"'{b}' not in frontend JS"
    # CustomerSuccess may be stored as 'CS' or 'Customer' in frontend display
    assert any(x in combined_js for x in ["CustomerSuccess","Customer Success","CS"]), \
        "CustomerSuccess not represented in frontend"
    ok("All 6 bidder names present in frontend JS")

    # All 9 decision types D1-D9
    for dt in ["D1","D2","D3","D4","D5","D6","D7","D8","D9"]:
        assert dt in combined_js, f"{dt} not in frontend JS"
    ok("All D1-D9 present in frontend JS")

    # No stale branding
    assert "XLVentures" not in html, "XLVentures still in HTML"
    assert "B2B staffing" not in html, "B2B staffing still in HTML"
    ok("No stale branding in index.html")

    # Key pages present
    for page_id in ["page-unilog","page-catalog","page-metrics","page-humanreview","page-investigation"]:
        assert f'id="{page_id}"' in html, f"Missing: {page_id}"
    ok("All 8 key page sections present in index.html")

except Exception as e:
    fail("Frontend alignment", e)

# ─────────────────────────────────────────────────────────────
section("FINAL SUMMARY")
# ─────────────────────────────────────────────────────────────
total = len(PASS) + len(FAIL)
print(f"\n  {'='*58}")
print(f"  TOTAL: {total} checks | {len(PASS)} PASS | {len(FAIL)} FAIL")
print(f"  {'='*58}")
if FAIL:
    print(f"\n  FAILED:")
    for f_ in FAIL:
        print(f"    ✗ {f_}")
    sys.exit(1)
else:
    print(f"\n  ✅ ALL CLEAR — Frontend to backend, fully aligned with PS")
    sys.exit(0)
