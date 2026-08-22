"""
Catalog Intelligence — Async Batch Job Tracker (§Catalog)

Manages batch catalog processing jobs with live progress updates and SSE streaming.
Supports multiple files in one batch job with full deduplication.
"""

from __future__ import annotations

import uuid
import asyncio
from datetime import datetime
from typing import Optional, Any

from backend.catalog.catalog_database import catalog_db, compute_canonical_hash
from backend.catalog.catalog_models import (
    Product, ProductField, FieldEvidence,
    ProductStatus, FieldStatus, RawSourceType
)
from backend.catalog.ingestion import parse_uploaded_file
from backend.catalog.cleaning import clean_and_normalize
from backend.catalog.catalog_validation import validate_all_product_fields
from backend.catalog.catalog_enrichment import enrich_product_missing_fields


class CatalogJobTracker:
    """In-memory batch job progress tracker for catalog processing."""

    def __init__(self):
        self._jobs: dict[str, dict[str, Any]] = {}

    def create_job(self, filenames: list[str] | str, total_items: int = 0) -> str:
        job_id = str(uuid.uuid4())
        if isinstance(filenames, str):
            filenames = [filenames]
        self._jobs[job_id] = {
            "job_id": job_id,
            "filenames": filenames,
            "status": "pending",  # pending, processing, completed, error
            "progress_percent": 0.0,
            "messages": [],
            "created_product_ids": [],
            "total_items": total_items,
            "processed_items": 0,
            "created_products": 0,
            "duplicate_products": 0,
            "failed_products": 0,
            "fields_created": 0,
            "fields_flagged": 0,
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "error": None,
        }
        self.add_message(
            job_id,
            f"Batch job initialized for {len(filenames)} file(s): {', '.join(filenames)}.",
            0.0
        )
        return job_id

    def add_message(self, job_id: str, message: str, percent: float | None = None) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        timestamp = datetime.utcnow().strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {message}"
        job["messages"].append(formatted_msg)
        if percent is not None:
            job["progress_percent"] = min(100.0, max(0.0, round(percent, 1)))

    def get_job(self, job_id: str) -> Optional[dict[str, Any]]:
        return self._jobs.get(job_id)

    def get_progress_messages(self, job_id: str) -> list[str]:
        job = self._jobs.get(job_id)
        return job["messages"] if job else []


job_tracker = CatalogJobTracker()


async def run_batch_job_multi(
    job_id: str,
    file_payloads: list[dict],  # list of {"filename": str, "bytes": bytes}
    product_name: Optional[str] = None,
):
    """
    Asynchronously processes multiple catalog files in one batch job:
    For each file: Ingestion → Cleaning → Deduplication → Validation → Enrichment.
    Updates job progress and SSE messages after each product.
    Deduplicates both within the batch and against existing DB records.
    """
    job = job_tracker.get_job(job_id)
    if not job:
        return

    try:
        job["status"] = "processing"
        job_tracker.add_message(job_id, f"Starting batch pipeline for {len(file_payloads)} file(s)...", 5.0)

        # ── Phase 1: Parse all files ─────────────────────────────────────
        all_raw_products = []
        for fp in file_payloads:
            filename = fp["filename"]
            file_bytes = fp["bytes"]
            job_tracker.add_message(job_id, f"Parsing '{filename}'...", None)
            try:
                raw_products = parse_uploaded_file(file_bytes, filename, product_name)
                for rp in raw_products:
                    rp["_source_file"] = filename
                all_raw_products.extend(raw_products)
                job_tracker.add_message(job_id, f"  → '{filename}': {len(raw_products)} product candidate(s) found.", None)
            except Exception as e:
                job_tracker.add_message(job_id, f"  ❌ Failed to parse '{filename}': {e}", None)

        total_p = len(all_raw_products)
        job["total_items"] = total_p

        if total_p == 0:
            job["status"] = "error"
            job["error"] = "No product data found in any uploaded file."
            job_tracker.add_message(job_id, "❌ No product data extracted from any file.", 0.0)
            return

        job_tracker.add_message(
            job_id,
            f"Extracted {total_p} product candidate(s) across {len(file_payloads)} file(s). "
            f"Starting ingestion pipeline...",
            10.0
        )

        # ── Phase 2: Ingest with deduplication ──────────────────────────
        created_pids = []
        created_count = 0
        duplicate_count = 0
        failed_count = 0
        total_fields_created = 0
        total_fields_flagged = 0

        # Track hashes seen in this batch to deduplicate within-batch
        batch_seen_hashes: set[str] = set()

        for i, raw_p in enumerate(all_raw_products, 1):
            p_name = raw_p.get("product_name", f"Product #{i}")
            src_file = raw_p.get("_source_file", "unknown")
            pct_start = 10.0 + ((i - 1) / total_p) * 80.0

            job_tracker.add_message(
                job_id,
                f"[{i}/{total_p}] '{p_name}' ({src_file}): Cleaning & Normalizing...",
                pct_start
            )

            try:
                cleaned_p = clean_and_normalize(raw_p)
                fields_data = cleaned_p.get("fields", [])
                canon_hash = compute_canonical_hash(cleaned_p["product_name"], fields_data)

                # Within-batch deduplication
                if canon_hash in batch_seen_hashes:
                    duplicate_count += 1
                    job_tracker.add_message(
                        job_id,
                        f"  ⚠ DUPLICATE (within batch): '{p_name}' — skipped.",
                        None
                    )
                    job["processed_items"] = i
                    continue

                # DB deduplication
                existing = catalog_db.get_product_by_canonical_hash(canon_hash)
                if existing:
                    duplicate_count += 1
                    catalog_db.update_product_timestamp(existing["id"])
                    job_tracker.add_message(
                        job_id,
                        f"  ⚠ DUPLICATE (in DB): '{p_name}' → existing product {existing['id'][:8]}... — skipped.",
                        None
                    )
                    job["processed_items"] = i
                    continue

                # New product — ingest
                batch_seen_hashes.add(canon_hash)
                p_obj = Product(
                    name=cleaned_p["product_name"],
                    raw_source_type=cleaned_p["raw_source_type"] or RawSourceType.MANUAL,
                    status=ProductStatus.INGESTED,
                    canonical_hash=canon_hash,
                )
                catalog_db.save_product(p_obj)
                created_pids.append(p_obj.id)
                created_count += 1

                for f_data in fields_data:
                    f_status = f_data.get("status", FieldStatus.RAW)
                    if f_status == FieldStatus.FLAGGED:
                        total_fields_flagged += 1
                    else:
                        total_fields_created += 1

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

                # Validate
                job_tracker.add_message(
                    job_id,
                    f"  → Validating fields for '{p_name}'...",
                    pct_start + (25.0 / total_p)
                )
                val_result = validate_all_product_fields(p_obj.id)

                # Enrich
                job_tracker.add_message(
                    job_id,
                    f"  → Inferring missing attributes for '{p_name}'...",
                    pct_start + (50.0 / total_p)
                )
                enr_result = enrich_product_missing_fields(p_obj.id)
                mode = enr_result.get("enrichment_mode", "deterministic_fallback")

                job_tracker.add_message(
                    job_id,
                    f"  ✓ '{p_name}': {val_result.get('validated_count', 0)} validated, "
                    f"{val_result.get('flagged_count', 0)} flagged, "
                    f"{enr_result.get('enriched_count', 0)} enriched ({mode}).",
                    None
                )

            except Exception as e:
                failed_count += 1
                job_tracker.add_message(job_id, f"  ❌ Failed to process '{p_name}': {e}", None)

            job["processed_items"] = i
            await asyncio.sleep(0.05)  # Yield to asyncio event loop

        # ── Phase 3: Complete ─────────────────────────────────────────────
        job["created_product_ids"] = created_pids
        job["created_products"] = created_count
        job["duplicate_products"] = duplicate_count
        job["failed_products"] = failed_count
        job["fields_created"] = total_fields_created
        job["fields_flagged"] = total_fields_flagged
        job["status"] = "completed"
        job["completed_at"] = datetime.utcnow().isoformat()
        job_tracker.add_message(
            job_id,
            (
                f"✓ Batch complete! Created: {created_count} | "
                f"Duplicates skipped: {duplicate_count} | "
                f"Failed: {failed_count} | "
                f"Total candidates: {total_p}"
            ),
            100.0
        )

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job_tracker.add_message(job_id, f"❌ Batch job failed: {str(e)}")
