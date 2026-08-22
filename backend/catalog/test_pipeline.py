"""
Catalog Intelligence -- Pipeline Verification Test Script

Tests the full catalog pipeline and verifies actual DB state.
Does NOT use mock responses -- inspects real DB records.

Usage:
  python -m backend.catalog.test_pipeline
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pathlib import Path
from backend.catalog.catalog_database import catalog_db, compute_canonical_hash
from backend.catalog.catalog_models import ProductStatus, FieldStatus, RawSourceType, Product, ProductField, FieldEvidence, EnrichmentMethod
from backend.catalog.ingestion import parse_uploaded_file
from backend.catalog.cleaning import clean_and_normalize
from backend.catalog.catalog_validation import validate_all_product_fields
from backend.catalog.catalog_enrichment import enrich_product_missing_fields, get_enrichment_mode, enrich_missing_field
from backend.catalog.catalog_explanation import explain_field

FIXTURE_CSV = Path(__file__).parent / "test_catalog.csv"
PASS = "[PASS]"
FAIL = "[FAIL]"
WARN = "[WARN]"


def ingest_file_idempotent(file_bytes: bytes, filename: str):
    """Ingest a file using the same deduplication logic as catalog_api.py /upload."""
    raw_products = parse_uploaded_file(file_bytes, filename)
    created = []
    duplicates = []

    for raw_p in raw_products:
        try:
            cleaned_p = clean_and_normalize(raw_p)
            fields_data = cleaned_p.get("fields", [])
            canon_hash = compute_canonical_hash(cleaned_p["product_name"], fields_data)

            existing = catalog_db.get_product_by_canonical_hash(canon_hash)
            if existing:
                duplicates.append(existing["id"])
                catalog_db.update_product_timestamp(existing["id"])
                continue

            p_obj = Product(
                name=cleaned_p["product_name"],
                raw_source_type=cleaned_p["raw_source_type"] or RawSourceType.MANUAL,
                status=ProductStatus.INGESTED,
                canonical_hash=canon_hash,
            )
            catalog_db.save_product(p_obj)
            created.append(p_obj.id)

            for f_data in fields_data:
                pf_obj = ProductField(
                    product_id=p_obj.id,
                    field_name=f_data["field_name"],
                    value=f_data.get("value"),
                    unit=f_data.get("unit"),
                    status=f_data.get("status", FieldStatus.RAW),
                    confidence=f_data.get("confidence"),
                )
                catalog_db.save_product_field(pf_obj)
                for ev_data in f_data.get("evidence", []):
                    fe = FieldEvidence(
                        product_field_id=pf_obj.id,
                        source_label=ev_data["source_label"],
                        raw_value=ev_data["raw_value"],
                    )
                    catalog_db.save_field_evidence(fe)
        except Exception as e:
            print(f"  Error processing product: {e}")

    return created, duplicates


def run_tests():
    results = []

    print("\n" + "=" * 60)
    print("VERIDEX CATALOG PIPELINE -- TRUSTWORTHY ENRICHMENT VERIFICATION")
    print("=" * 60)

    # Clear previous test data
    print("\n[PRE-TEST] Clearing catalog data for clean test run...")
    counts = catalog_db.clear_catalog_data()
    print(f"  Cleared: {counts['products_removed']} products, "
          f"{counts['fields_removed']} fields, "
          f"{counts['evidence_removed']} evidence rows.")

    file_bytes = FIXTURE_CSV.read_bytes()
    filename = "test_catalog.csv"

    # TEST 1: First Upload
    print("\n[TEST 1] First upload of test_catalog.csv")
    created1, dupes1 = ingest_file_idempotent(file_bytes, filename)
    expected_created = 5
    ok = len(created1) == expected_created and len(dupes1) == 0
    print(f"  {PASS if ok else FAIL} -- created={len(created1)} (expected {expected_created}), "
          f"duplicates={len(dupes1)} (expected 0)")
    results.append(("TEST 1: First upload", ok))

    # TEST 2: Duplicate Upload
    print("\n[TEST 2] Second upload (same file -- duplicate detection)")
    products_before = len(catalog_db.get_all_products())
    created2, dupes2 = ingest_file_idempotent(file_bytes, filename)
    products_after = len(catalog_db.get_all_products())
    ok = (len(created2) == 0 and len(dupes2) == expected_created and products_before == products_after)
    print(f"  {PASS if ok else FAIL} -- created={len(created2)} (expected 0), "
          f"duplicates={len(dupes2)} (expected {expected_created})")
    print(f"  {PASS if products_before == products_after else FAIL} -- "
          f"total_products unchanged: {products_before} -> {products_after}")
    results.append(("TEST 2: Duplicate detection", ok))

    # TEST 3: Upload a genuinely different product
    print("\n[TEST 3] Upload a genuinely different product (should increment)")
    different_csv = b"name,weight,voltage,material\nUniqueProduct XZ-999,100 kg,380 V,Titanium\n"
    created3, dupes3 = ingest_file_idempotent(different_csv, "unique_product.csv")
    products_final = len(catalog_db.get_all_products())
    ok = len(created3) == 1 and len(dupes3) == 0 and products_final == expected_created + 1
    print(f"  {PASS if ok else FAIL} -- created={len(created3)} (expected 1), "
          f"total_products={products_final} (expected {expected_created + 1})")
    results.append(("TEST 3: New different product", ok))

    products = catalog_db.get_all_products()

    # TEST 4: Validation -- Valid Fields
    print("\n[TEST 4] Validation -- checking a valid product (ProPump 5000)")
    propump = next((p for p in products if "propump" in p["name"].lower() or "ProPump" in p["name"]), products[0])
    val_result = validate_all_product_fields(propump["id"])
    validated = val_result.get("validated_count", 0)
    ok = validated > 0
    print(f"  {PASS if ok else FAIL} -- '{propump['name']}': "
          f"{validated} validated, {val_result.get('flagged_count', 0)} flagged")
    db_fields = catalog_db.get_product_fields(propump["id"])
    db_validated = sum(1 for f in db_fields if f["status"] == "validated")
    print(f"  DB confirmation: {db_validated} fields with status='validated' in database")
    ok2 = db_validated > 0
    print(f"  {PASS if ok2 else FAIL} -- DB state confirms validation occurred")
    results.append(("TEST 4: Valid product validation", ok and ok2))

    # TEST 5: Validation -- Invalid Fields
    print("\n[TEST 5] Validation -- invalid fields (negative weight, 'unknown' voltage)")
    solar = next((p for p in products if "solar" in p["name"].lower()), None)
    if solar:
        val_result2 = validate_all_product_fields(solar["id"])
        flagged = val_result2.get("flagged_count", 0)
        ok = flagged > 0
        print(f"  {PASS if ok else FAIL} -- '{solar['name']}': {flagged} flagged (expected >0)")
        db_fields2 = catalog_db.get_product_fields(solar["id"])
        db_flagged = sum(1 for f in db_fields2 if f["status"] == "flagged")
        db_reasons = [(f["field_name"], f.get("validation_reason", "")) for f in db_fields2 if f["status"] == "flagged"]
        print(f"  DB confirmation: {db_flagged} fields with status='flagged'")
        for fname, reason in db_reasons:
            print(f"    Field '{fname}': {reason[:100]}")
        ok2 = db_flagged > 0
        print(f"  {PASS if ok2 else FAIL} -- DB state confirms flagged fields with reasons stored")
        results.append(("TEST 5: Invalid field flagging", ok and ok2))
    else:
        print(f"  {WARN} -- SolarPanel product not found, skipping")
        results.append(("TEST 5: Invalid field flagging", None))

    # TEST 6: ANTI-HALLUCINATION TEST — Missing certification must NOT fabricate "Industrial Duty Rated"
    print("\n[TEST 6] Anti-Hallucination: 'Industrial Heavy Duty Water Pump' certification test")
    # Ingest a product with "Industrial Heavy Duty Water Pump" without explicit certification
    pump_test_csv = b"name,voltage,weight\nIndustrial Heavy Duty Water Pump,240 V,45 kg\n"
    created_pump, _ = ingest_file_idempotent(pump_test_csv, "industrial_pump.csv")
    pump_id = created_pump[0] if created_pump else propump["id"]
    
    enr_res = enrich_product_missing_fields(pump_id)
    pump_fields = catalog_db.get_product_fields(pump_id)
    cert_field = next((f for f in pump_fields if f["field_name"].lower() == "certification"), None)

    ok_cert = cert_field is not None and cert_field.get("value") != "Industrial Duty Rated" and (
        cert_field.get("value") == "Unknown" or cert_field.get("status") in ("needs_review", "missing")
    )
    print(f"  {PASS if ok_cert else FAIL} -- Certification value = '{cert_field.get('value') if cert_field else 'None'}' "
          f"(status: {cert_field.get('status') if cert_field else 'None'})")
    if cert_field:
        print(f"    Reasoning stored: '{cert_field.get('reasoning') or cert_field.get('validation_reason')}'")
    results.append(("TEST 6: Anti-hallucination guardrail (no fake certification)", ok_cert))

    # TEST 7: Trustworthy Category Inference
    print("\n[TEST 7] Evidence-based Category Inference (Pumps -> 'Industrial Pumps')")
    cat_field = next((f for f in pump_fields if f["field_name"].lower() == "category"), None)
    ok_cat = cat_field is not None and cat_field.get("value") == "Industrial Pumps" and cat_field.get("status") == "inferred"
    print(f"  {PASS if ok_cat else FAIL} -- Category value = '{cat_field.get('value') if cat_field else 'None'}' "
          f"(status: {cat_field.get('status') if cat_field else 'None'}, confidence: {cat_field.get('confidence') if cat_field else 'None'})")
    results.append(("TEST 7: Trustworthy category inference", ok_cat))

    # TEST 8: Enrichment Mode & Honest Labeling
    print("\n[TEST 8] Enrichment mode and source labeling honesty")
    mode = get_enrichment_mode()
    has_key = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    expected_mode = "LLM" if has_key else "deterministic_fallback"
    ok_mode = mode == expected_mode
    print(f"  {PASS if ok_mode else FAIL} -- Mode='{mode}' (expected '{expected_mode}')")
    results.append(("TEST 8: Enrichment mode label honesty", ok_mode))

    # TEST 9: Explanation with Provenance & Human Verification Checkpoint
    print("\n[TEST 9] Explanation engine -- provenance & human verification recommendation")
    p_full = catalog_db.get_product_with_details(pump_id)
    tested_exp = False
    for f in p_full.get("fields", []):
        exp = explain_field(f, f.get("evidence", []))
        if exp and exp.get("explanation"):
            ok = "Human Checkpoint" in exp["explanation"] and bool(exp.get("provenance"))
            print(f"  {PASS if ok else FAIL} -- Explanation for '{f['field_name']}':")
            print(f"    Provenance: {exp.get('provenance')}")
            rec_safe = exp.get('human_review_rec', '').encode('ascii', 'replace').decode('ascii')
            print(f"    Human Checkpoint: {exp.get('human_review_badge')} ({rec_safe[:50]}...)")
            tested_exp = True
            results.append(("TEST 9: Explanation & human verification", ok))
            break
    if not tested_exp:
        results.append(("TEST 9: Explanation & human verification", False))

    # TEST 10: Dashboard Summary with 5-Way Field Split
    print("\n[TEST 10] Dashboard summary with verified, validated, llm, rule, and needs_review split")
    dash = catalog_db.get_dashboard_summary()
    tp = dash.get("total_products", 0)
    tf = dash.get("total_fields", 0)
    has_keys = all(k in dash for k in ("fields_verified", "fields_validated", "fields_llm_enriched", "fields_rule_inferred", "fields_needs_review_count"))
    ok_dash = tp > 0 and tf > 0 and has_keys
    print(f"  {PASS if ok_dash else FAIL} -- total_products={tp}, total_fields={tf}")
    print(f"    Verified={dash.get('fields_verified')}, Validated={dash.get('fields_validated')}, "
          f"LLM Enriched={dash.get('fields_llm_enriched')}, Rule Inferred={dash.get('fields_rule_inferred')}, "
          f"Needs Review={dash.get('fields_needs_review_count')}")
    print(f"    Pipeline stages: {dash.get('pipeline_stages')}")
    results.append(("TEST 10: Dashboard metrics split", ok_dash))

    # Summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, r in results if r is True)
    failed = sum(1 for _, r in results if r is False)
    warned = sum(1 for _, r in results if r is None)
    for name, result in results:
        icon = PASS if result is True else (WARN if result is None else FAIL)
        print(f"  {icon}  {name}")
    print(f"\nTotal: {passed} passed, {failed} failed, {warned} warnings")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
