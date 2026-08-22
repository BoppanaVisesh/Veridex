"""
End-to-End API Integration Test Suite for Veridex & Catalog Intelligence

Uses FastAPI TestClient to test the complete server API surface:
1. Core Veridex endpoints (/api/health, /api/decisions, /api/scenarios)
2. All Catalog Intelligence endpoints with full request/response validation
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

PASS = "[PASS]"
FAIL = "[FAIL]"

def run_api_tests():
    results = []
    print("\n" + "=" * 60)
    print("VERIDEX & CATALOG API INTEGRATION TESTS")
    print("=" * 60)

    # ── 1. Core Veridex Endpoints (No Regressions) ──
    print("\n[CORE 1] GET /api/health")
    res = client.get("/api/health")
    ok = res.status_code == 200 and res.json().get("status") == "healthy"
    print(f"  {PASS if ok else FAIL} -- status_code={res.status_code}, data={res.json()}")
    results.append(("CORE 1: Health check", ok))

    print("\n[CORE 2] GET /api/decisions")
    res = client.get("/api/decisions")
    data = res.json()
    ok = res.status_code == 200 and "decisions" in data and isinstance(data["decisions"], list)
    print(f"  {PASS if ok else FAIL} -- status_code={res.status_code}, count={len(data.get('decisions', []))}")
    results.append(("CORE 2: Decisions list", ok))

    print("\n[CORE 3] GET /api/scenarios")
    res = client.get("/api/scenarios")
    scenarios_data = res.json()
    ok = res.status_code == 200 and isinstance(scenarios_data, dict) and len(scenarios_data) > 0
    print(f"  {PASS if ok else FAIL} -- status_code={res.status_code}, scenarios_count={len(scenarios_data)}")
    results.append(("CORE 3: Scenarios list", ok))

    # ── 2. Catalog Health & Config ──
    print("\n[CATALOG 1] GET /api/catalog/health")
    res = client.get("/api/catalog/health")
    ok = res.status_code == 200 and res.json().get("status") == "ok"
    print(f"  {PASS if ok else FAIL} -- status_code={res.status_code}, data={res.json()}")
    results.append(("CATALOG 1: Catalog health", ok))

    print("\n[CATALOG 2] GET /api/catalog/enrichment-mode")
    res = client.get("/api/catalog/enrichment-mode")
    data = res.json()
    ok = res.status_code == 200 and data.get("enrichment_mode") in ("LLM", "deterministic_fallback")
    print(f"  {PASS if ok else FAIL} -- mode={data.get('enrichment_mode')}, has_key={data.get('gemini_api_key_configured')}")
    results.append(("CATALOG 2: Enrichment mode status", ok))

    # ── 3. Clear Demo Data ──
    print("\n[CATALOG 3] POST /api/catalog/clear-demo-data (with confirmation)")
    res = client.post("/api/catalog/clear-demo-data", data={"confirmed": "true"})
    ok = res.status_code == 200 and res.json().get("status") == "cleared"
    print(f"  {PASS if ok else FAIL} -- status_code={res.status_code}, removed={res.json().get('products_removed')}")
    results.append(("CATALOG 3: Clear demo data", ok))

    # ── 4. Dashboard Summary (Empty State) ──
    print("\n[CATALOG 4] GET /api/catalog/dashboard (after clear)")
    res = client.get("/api/catalog/dashboard")
    dash = res.json()
    ok = res.status_code == 200 and dash.get("total_products") == 0 and dash.get("total_fields") == 0
    print(f"  {PASS if ok else FAIL} -- total_products={dash.get('total_products')}, total_fields={dash.get('total_fields')}")
    results.append(("CATALOG 4: Empty dashboard summary", ok))

    # ── 5. Single Upload (New Products) ──
    print("\n[CATALOG 5] POST /api/catalog/upload (single CSV upload)")
    csv_content = (
        "name,weight,voltage,material,dimensions,category,certification\n"
        "Apex Turbine TX-1,120 kg,440 V,Stainless Steel,600x400x400 mm,Generators,CE Marked\n"
        "VoltSensor S-10,-5 kg,unknown,Plastic,100x50x20 mm,Electrical,\n"
    )
    files = {"file": ("apex_turbine.csv", csv_content.encode("utf-8"), "text/csv")}
    res = client.post("/api/catalog/upload", files=files)
    up_data = res.json()
    ok = res.status_code == 200 and up_data.get("created_products") == 2 and up_data.get("duplicate_products") == 0
    print(f"  {PASS if ok else FAIL} -- created={up_data.get('created_products')}, dupes={up_data.get('duplicate_products')}")
    results.append(("CATALOG 5: Single upload", ok))

    # ── 6. Single Upload (Duplicate Detection) ──
    print("\n[CATALOG 6] POST /api/catalog/upload (duplicate upload -- same file)")
    files2 = {"file": ("apex_turbine.csv", csv_content.encode("utf-8"), "text/csv")}
    res = client.post("/api/catalog/upload", files=files2)
    up_data2 = res.json()
    ok = res.status_code == 200 and up_data2.get("created_products") == 0 and up_data2.get("duplicate_products") == 2
    print(f"  {PASS if ok else FAIL} -- created={up_data2.get('created_products')} (exp 0), dupes={up_data2.get('duplicate_products')} (exp 2)")
    results.append(("CATALOG 6: Idempotent duplicate rejection", ok))

    # ── 7. Products List ──
    print("\n[CATALOG 7] GET /api/catalog/products")
    res = client.get("/api/catalog/products")
    products = res.json()
    ok = res.status_code == 200 and len(products) == 2
    print(f"  {PASS if ok else FAIL} -- product_count={len(products)}")
    results.append(("CATALOG 7: Products list", ok))

    # ── 8. Product Details ──
    # Find VoltSensor (has invalid field) and Apex Turbine (valid)
    volt_prod = next(p for p in products if "VoltSensor" in p["name"])
    apex_prod = next(p for p in products if "Apex" in p["name"])

    print(f"\n[CATALOG 8] GET /api/catalog/products/{apex_prod['id']}")
    res = client.get(f"/api/catalog/products/{apex_prod['id']}")
    p_detail = res.json()
    ok = res.status_code == 200 and p_detail.get("id") == apex_prod["id"] and len(p_detail.get("fields", [])) > 0
    print(f"  {PASS if ok else FAIL} -- product_name='{p_detail.get('name')}', fields_count={len(p_detail.get('fields', []))}")
    results.append(("CATALOG 8: Product detail", ok))

    # ── 9. Validation Endpoint (Flagged Invalid Field) ──
    print(f"\n[CATALOG 9] POST /api/catalog/products/{volt_prod['id']}/validate (VoltSensor with -5kg weight)")
    res = client.post(f"/api/catalog/products/{volt_prod['id']}/validate")
    val_data = res.json()
    flagged = val_data.get("flagged_count", 0)
    ok = res.status_code == 200 and flagged > 0
    print(f"  {PASS if ok else FAIL} -- validated={val_data.get('validated_count')}, flagged={flagged} (expected >0 for -5kg)")
    results.append(("CATALOG 9: Field validation", ok))

    # ── 10. Enrichment Endpoint ──
    print(f"\n[CATALOG 10] POST /api/catalog/products/{volt_prod['id']}/enrich")
    res = client.post(f"/api/catalog/products/{volt_prod['id']}/enrich")
    enr_data = res.json()
    ok = res.status_code == 200 and "enrichment_mode" in enr_data
    print(f"  {PASS if ok else FAIL} -- mode='{enr_data.get('enrichment_mode')}', enriched_count={enr_data.get('enriched_count')}")
    results.append(("CATALOG 10: Field enrichment", ok))

    # ── 11. Explanation Endpoint ──
    field_to_explain = p_detail["fields"][0]["field_name"]
    print(f"\n[CATALOG 11] GET /api/catalog/products/{apex_prod['id']}/explain/{field_to_explain}")
    res = client.get(f"/api/catalog/products/{apex_prod['id']}/explain/{field_to_explain}")
    exp_data = res.json()
    ok = res.status_code == 200 and bool(exp_data.get("explanation")) and exp_data.get("field_name") == field_to_explain
    prov = (exp_data.get("provenance") or "").replace("\u2192", "->")
    print(f"  {PASS if ok else FAIL} -- field='{exp_data.get('field_name')}', provenance='{prov}'")
    results.append(("CATALOG 11: Field explanation", ok))

    # ── 12. Pipeline Smoke-Check Endpoint ──
    print("\n[CATALOG 12] POST /api/catalog/pipeline-check")
    res = client.post("/api/catalog/pipeline-check")
    pipe_res = res.json()
    ok = res.status_code == 200 and pipe_res.get("result") in ("PASS", "WARN")
    print(f"  {PASS if ok else FAIL} -- result='{pipe_res.get('result')}', stages={list(pipe_res.get('stages', {}).keys())}")
    results.append(("CATALOG 12: Pipeline verification smoke check", ok))

    # ── Summary ──
    print("\n" + "=" * 60)
    print("API INTEGRATION TEST SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, r in results if r is True)
    failed = sum(1 for _, r in results if r is False)
    for name, result in results:
        icon = PASS if result is True else FAIL
        print(f"  {icon}  {name}")
    print(f"\nTotal: {passed} passed, {failed} failed out of {len(results)}")
    print("=" * 60)

    return failed == 0

if __name__ == "__main__":
    success = run_api_tests()
    sys.exit(0 if success else 1)
