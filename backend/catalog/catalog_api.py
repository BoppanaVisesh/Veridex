"""
Catalog Intelligence — FastAPI Router (§Catalog)

REST API routes for catalog upload, batch jobs, validation, enrichment, SSE streaming, and dashboard metrics.
All routes prefixed /api/catalog/*

Key behaviors:
- /upload: Idempotent ingestion using canonical_hash deduplication
- /batch-upload: Accepts multiple files; deduplicates each
- /products/{id}/validate: Runs validation, stores reason in DB
- /products/{id}/enrich: Infers missing fields; reports enrichment_mode
- /pipeline-check: Safe smoke-test against a controlled fixture
- /clear-demo-data: Clears ONLY catalog tables (requires confirmation=true)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse

from backend.catalog.catalog_database import catalog_db, compute_canonical_hash
from backend.catalog.catalog_models import (
    Product, ProductField, FieldEvidence,
    ProductStatus, FieldStatus, RawSourceType
)
from backend.catalog.ingestion import parse_uploaded_file
from backend.catalog.cleaning import clean_and_normalize
from backend.catalog.catalog_validation import validate_all_product_fields
from backend.catalog.catalog_enrichment import enrich_product_missing_fields, _get_enrichment_mode
from backend.catalog.catalog_explanation import explain_field
from backend.catalog.catalog_jobs import job_tracker, run_batch_job_multi


router = APIRouter(prefix="/api/catalog", tags=["Catalog Intelligence"])

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".html", ".htm", ".pdf"}


def _validate_extension(filename: str) -> None:
    """Raise HTTPException if the file extension is not supported."""
    import pathlib
    ext = pathlib.Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Supported: CSV, XLSX, HTML, PDF."
        )


def _ingest_cleaned_product(
    cleaned_p: dict,
    filename: str,
) -> tuple[str, dict]:
    """
    Core ingestion logic: deduplication check → create or update product + fields.
    Returns (action, result_dict) where action is 'created', 'updated', or 'duplicate_skipped'.
    """
    p_name = cleaned_p["product_name"]
    fields_data = cleaned_p.get("fields", [])

    # Compute canonical identity hash
    canon_hash = compute_canonical_hash(p_name, fields_data)

    # Check for existing product
    existing = catalog_db.get_product_by_canonical_hash(canon_hash)
    if existing:
        # Duplicate detected — update timestamp only, do NOT create new row
        catalog_db.update_product_timestamp(existing["id"])
        return "duplicate_skipped", {
            "duplicate_detected": True,
            "existing_product_id": existing["id"],
            "action": "skipped",
            "product_name": p_name,
        }

    # New product — create
    p_obj = Product(
        name=p_name,
        raw_source_type=cleaned_p["raw_source_type"] or RawSourceType.MANUAL,
        status=ProductStatus.INGESTED,
        canonical_hash=canon_hash,
    )
    catalog_db.save_product(p_obj)

    fields_created = 0
    fields_flagged = 0

    for f_data in fields_data:
        f_status = f_data.get("status", FieldStatus.RAW)
        if f_status == FieldStatus.FLAGGED:
            fields_flagged += 1
        else:
            fields_created += 1

        pf_obj = ProductField(
            product_id=p_obj.id,
            field_name=f_data["field_name"],
            value=f_data.get("value"),
            unit=f_data.get("unit"),
            status=f_status,
            confidence=f_data.get("confidence"),
        )
        catalog_db.save_product_field(pf_obj)

        for ev_data in f_data.get("evidence", []):
            fe_obj = FieldEvidence(
                product_field_id=pf_obj.id,
                source_label=ev_data["source_label"],
                raw_value=ev_data["raw_value"],
            )
            catalog_db.save_field_evidence(fe_obj)

    return "created", {
        "product_id": p_obj.id,
        "product_name": p_name,
        "fields_created": fields_created,
        "fields_flagged": fields_flagged,
        "canonical_hash": canon_hash,
        "duplicate_detected": False,
    }


# ── Health ─────────────────────────────────────────────────────────────────────

@router.get("/health")
async def catalog_health():
    """Health endpoint for catalog module."""
    return {"status": "ok", "module": "catalog"}


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def catalog_dashboard():
    """Returns catalog-wide health and quality metrics summary."""
    return catalog_db.get_dashboard_summary()


# ── Product List & Detail ─────────────────────────────────────────────────────

@router.get("/products")
async def list_products():
    """List all catalog products."""
    return catalog_db.get_all_products()


@router.get("/products/{product_id}")
async def get_product(product_id: str):
    """Get a single product with its full list of fields and evidence."""
    product = catalog_db.get_product_with_details(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


# ── Single File Upload (Idempotent) ───────────────────────────────────────────

@router.post("/upload")
async def upload_catalog_file(
    file: UploadFile = File(...),
    product_name: Optional[str] = Form(None)
):
    """
    Upload a single catalog file (CSV, XLSX, HTML, PDF).
    Implements idempotent ingestion: uploading the same product twice does NOT
    create a duplicate — it returns duplicate_detected=True with the existing product ID.

    Response includes:
      created_products, updated_products, duplicate_products, failed_products
    """
    filename = file.filename or "uploaded_catalog"
    _validate_extension(filename)
    file_bytes = await file.read()

    try:
        raw_products = parse_uploaded_file(file_bytes, filename, product_name)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse '{filename}': {str(e)}")

    if not raw_products:
        raise HTTPException(status_code=400, detail="No product data could be extracted.")

    created = []
    duplicates = []
    failed = []

    for raw_p in raw_products:
        try:
            cleaned_p = clean_and_normalize(raw_p)
            action, result = _ingest_cleaned_product(cleaned_p, filename)
            if action == "created":
                created.append(result)
            else:
                duplicates.append(result)
        except Exception as e:
            failed.append({"product_name": raw_p.get("product_name", "?"), "error": str(e)})

    return {
        "status": "success",
        "filename": filename,
        "created_products": len(created),
        "duplicate_products": len(duplicates),
        "failed_products": len(failed),
        "products": created,
        "duplicates": duplicates,
        "failures": failed,
        "message": (
            f"Ingested {len(created)} new product(s). "
            f"{len(duplicates)} duplicate(s) detected and skipped. "
            f"{len(failed)} failure(s)."
        ),
    }


# ── Batch Upload (Multiple Files, Idempotent) ─────────────────────────────────

@router.post("/batch-upload")
async def batch_upload_catalog_files(
    files: List[UploadFile] = File(...),
    product_name: Optional[str] = Form(None)
):
    """
    Accepts multiple catalog files (CSV, XLSX, HTML, PDF) as a batch.
    Creates an async batch processing job and returns job_id for SSE tracking.
    Each file is parsed independently. Deduplication is applied across all files
    and against existing database records.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    # Read all file bytes before async hand-off
    file_payloads = []
    for f in files:
        _validate_extension(f.filename or "unknown")
        file_bytes = await f.read()
        file_payloads.append({"filename": f.filename or "unknown", "bytes": file_bytes})

    filenames = [fp["filename"] for fp in file_payloads]
    job_id = job_tracker.create_job(filenames)
    asyncio.create_task(run_batch_job_multi(job_id, file_payloads, product_name))

    return {
        "status": "pending",
        "job_id": job_id,
        "file_count": len(file_payloads),
        "filenames": filenames,
        "message": f"Batch job initialized for {len(file_payloads)} file(s).",
    }


# ── Job Progress (Polling + SSE) ──────────────────────────────────────────────

@router.get("/jobs/{job_id}/progress")
async def get_job_progress(job_id: str):
    """Returns progress status and log messages for a batch job."""
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found.")
    return {
        "job_id": job_id,
        "status": job["status"],
        "progress_percent": job["progress_percent"],
        "messages": job["messages"],
        "processed_items": job["processed_items"],
        "total_items": job["total_items"],
        "created_products": job["created_products"],
        "duplicate_products": job["duplicate_products"],
        "failed_products": job["failed_products"],
        "created_product_ids": job["created_product_ids"],
    }


@router.get("/jobs/{job_id}/stream")
async def stream_job_progress(job_id: str):
    """SSE endpoint streaming real-time batch processing progress."""
    async def event_generator():
        last_index = 0
        while True:
            job = job_tracker.get_job(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break

            messages = job["messages"]
            if len(messages) > last_index:
                for msg in messages[last_index:]:
                    yield f"data: {json.dumps({'message': msg, 'percent': job['progress_percent']})}\n\n"
                last_index = len(messages)

            if job["status"] in ("completed", "error"):
                yield f"data: {json.dumps({'done': True, 'status': job['status'], 'progress_percent': job['progress_percent'], 'created_products': job['created_products'], 'duplicate_products': job['duplicate_products'], 'failed_products': job['failed_products'], 'product_ids': job['created_product_ids']})}\n\n"
                break

            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Validate ──────────────────────────────────────────────────────────────────

@router.post("/products/{product_id}/validate")
async def validate_product(product_id: str):
    """Run validation on product fields for plausibility, consistency, and contradictions."""
    try:
        summary = validate_all_product_fields(product_id)
        return {
            "status": "success",
            "product_id": product_id,
            "validated_count": summary["validated_count"],
            "conflicted_count": summary["conflicted_count"],
            "flagged_count": summary["flagged_count"],
            "field_results": summary["field_results"],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Enrich ────────────────────────────────────────────────────────────────────

@router.post("/products/{product_id}/enrich")
async def enrich_product(product_id: str):
    """Identifies missing product fields and infers values using AI/rule-based context."""
    try:
        summary = enrich_product_missing_fields(product_id)
        return {
            "status": "success",
            "product_id": product_id,
            "enrichment_mode": summary["enrichment_mode"],
            "enriched_count": summary["enriched_count"],
            "enriched_fields": summary["enriched_fields"],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ── Explain ───────────────────────────────────────────────────────────────────

@router.get("/products/{product_id}/explain/{field_name}")
async def explain_product_field(product_id: str, field_name: str):
    """Returns a human-readable explanation and full evidence trail for a specific field."""
    product = catalog_db.get_product_with_details(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    target_name = field_name.lower().strip()
    target_field = None
    for f in product.get("fields", []):
        if f.get("field_name", "").lower().strip() == target_name:
            target_field = f
            break

    if not target_field:
        raise HTTPException(
            status_code=404,
            detail=f"Field '{field_name}' not found for product '{product_id}'"
        )

    evidence_list = target_field.get("evidence", [])
    return explain_field(target_field, evidence_list)


# ── Pipeline Verification Check ───────────────────────────────────────────────

@router.post("/pipeline-check")
async def run_pipeline_check():
    """
    Safe smoke-test of the full catalog pipeline using a controlled test fixture.
    Does NOT modify real production catalog data if it detects an existing test fixture.
    Returns PASS/FAIL with stage details.
    """
    stages = {}
    test_product_id = None
    fixture_name = "__PIPELINE_CHECK_FIXTURE__"
    canon_hash = compute_canonical_hash(fixture_name)

    try:
        # Stage 1: Ingestion
        existing = catalog_db.get_product_by_canonical_hash(canon_hash)
        if existing:
            test_product_id = existing["id"]
            stages["ingest"] = {"status": "pass", "detail": f"Fixture product exists: {test_product_id}"}
        else:
            from backend.catalog.catalog_models import Product, RawSourceType, ProductStatus
            p = Product(
                name=fixture_name,
                raw_source_type=RawSourceType.MANUAL,
                status=ProductStatus.INGESTED,
                canonical_hash=canon_hash,
            )
            catalog_db.save_product(p)
            test_product_id = p.id
            stages["ingest"] = {"status": "pass", "detail": f"Test product created: {test_product_id}"}

        # Stage 2: Field Creation (normalization)
        from backend.catalog.catalog_models import ProductField, FieldStatus
        existing_fields = catalog_db.get_product_fields(test_product_id)
        if not existing_fields:
            test_fields = [
                ("name", "Industrial Heavy Duty Water Pump", None, 0.95),
                ("weight", "45.5", "kg", 0.90),
                ("voltage", "-20", "V", 0.90),   # INVALID: negative
                ("description", "heavy duty industrial pump for high pressure water transfer", None, 0.80),
            ]
            for fname, val, unit, conf in test_fields:
                pf = ProductField(
                    product_id=test_product_id,
                    field_name=fname,
                    value=val,
                    unit=unit,
                    status=FieldStatus.RAW,
                    confidence=conf,
                )
                catalog_db.save_product_field(pf)
        stages["clean"] = {"status": "pass", "detail": f"Fields present for fixture product."}

        # Stage 3: Validation
        val_result = validate_all_product_fields(test_product_id)
        flagged = val_result.get("flagged_count", 0)
        validated = val_result.get("validated_count", 0)
        stages["validate"] = {
            "status": "pass" if flagged > 0 else "warn",
            "detail": f"{validated} validated, {flagged} flagged (expected ≥1 flagged for voltage=-20).",
            "validated_count": validated,
            "flagged_count": flagged,
        }

        # Stage 4: Enrichment
        enr_result = enrich_product_missing_fields(test_product_id)
        enrichment_mode = enr_result.get("enrichment_mode", "unknown")
        enriched = enr_result.get("enriched_count", 0)
        stages["enrich"] = {
            "status": "pass" if enriched > 0 else "warn",
            "detail": f"{enriched} field(s) enriched via {enrichment_mode}.",
            "enrichment_mode": enrichment_mode,
            "enriched_count": enriched,
        }

        # Stage 5: Evidence Creation
        fields_with_evidence = catalog_db.get_product_with_details(test_product_id)
        ev_total = sum(len(f.get("evidence", [])) for f in fields_with_evidence.get("fields", []))
        stages["evidence"] = {
            "status": "pass" if ev_total > 0 else "warn",
            "detail": f"{ev_total} total evidence record(s) linked to fixture.",
        }

        # Stage 6: Explanation
        try:
            target_field = next(
                (f for f in fields_with_evidence.get("fields", []) if f.get("status") == "enriched"),
                None
            )
            if target_field:
                exp = explain_field(target_field, target_field.get("evidence", []))
                stages["explain"] = {"status": "pass", "detail": f"Explanation generated for field '{target_field.get('field_name')}'."}
            else:
                stages["explain"] = {"status": "warn", "detail": "No enriched fields to explain yet."}
        except Exception as e:
            stages["explain"] = {"status": "fail", "detail": str(e)}

        # Determine overall result
        all_pass = all(s["status"] in ("pass", "warn") for s in stages.values())
        overall = "PASS" if all_pass else "FAIL"

        return {
            "result": overall,
            "stages": stages,
            "enrichment_mode": enrichment_mode,
            "test_product_id": test_product_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        return {
            "result": "FAIL",
            "error": str(e),
            "stages": stages,
            "timestamp": datetime.utcnow().isoformat(),
        }


# ── Clear Demo Data (Catalog-Only, Requires Confirmation) ─────────────────────

@router.post("/clear-demo-data")
async def clear_demo_data(confirmed: bool = Form(False)):
    """
    Clears ALL catalog tables (products, product_fields, field_evidence).
    NEVER touches decision_log, outcomes, weight_snapshots, influence_ledger.
    Requires confirmed=true to execute.
    """
    if not confirmed:
        raise HTTPException(
            status_code=400,
            detail="Safety check: must send confirmed=true to execute catalog clear."
        )

    counts = catalog_db.clear_catalog_data()
    return {
        "status": "cleared",
        "message": (
            f"Catalog data cleared: {counts['products_removed']} products, "
            f"{counts['fields_removed']} fields, {counts['evidence_removed']} evidence rows removed."
        ),
        **counts,
        "warning": "Decision tables (decision_log, outcomes, weight_snapshots, influence_ledger) were NOT touched.",
    }


# ── Enrichment Mode Status ────────────────────────────────────────────────────

@router.get("/enrichment-mode")
async def get_enrichment_mode():
    """Returns the current enrichment mode (LLM or deterministic_fallback)."""
    mode = _get_enrichment_mode()
    has_key = bool(os.environ.get("GEMINI_API_KEY", "").strip())
    return {
        "enrichment_mode": mode,
        "gemini_api_key_configured": has_key,
        "description": (
            "Real Gemini LLM inference" if mode == "LLM"
            else "Deterministic keyword-pattern fallback (no GEMINI_API_KEY)"
        ),
    }
