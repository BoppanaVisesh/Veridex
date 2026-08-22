"""
Catalog Intelligence — Database Layer (SQLite)

Thread-safe persistent storage for catalog products, product fields, and evidence.
Reuses/extends DB connection pattern from backend/database.py without altering existing tables.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from backend.database import DB_PATH
from backend.catalog.catalog_models import (
    Product, ProductField, FieldEvidence,
    RawSourceType, ProductStatus, FieldStatus
)

import hashlib
import re


def compute_canonical_hash(product_name: str, fields: list[dict] | None = None) -> str:
    """
    Computes a deterministic canonical identity hash for a product.
    Normalizes product name (e.g. 'ProPump 5000', 'pro pump 5000' -> 'propump5000')
    and combines with key identifying attributes (model, sku, part_number, item_code) if available.
    
    Different products with different names will produce different hashes.
    Products with identical normalized names AND identical key attributes will match.
    """
    norm_name = re.sub(r'[^a-z0-9]', '', (product_name or '').lower())

    key_attrs = []
    if fields:
        for f in fields:
            f_name = (f.get("field_name") or "").lower().strip()
            val = (f.get("value") or "").lower().strip()
            if f_name in ("model", "sku", "part_number", "item_code") and val:
                norm_val = re.sub(r'[^a-z0-9]', '', val)
                key_attrs.append(f"{f_name}:{norm_val}")

    key_str = f"{norm_name}|" + "|".join(sorted(key_attrs))
    return hashlib.sha256(key_str.encode('utf-8')).hexdigest()


class CatalogDatabase:
    """Thread-safe SQLite database manager for catalog intelligence."""

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = str(db_path or DB_PATH)
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_db(self) -> None:
        """Create catalog tables if they don't exist and perform safe column migrations."""
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                raw_source_type TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS product_fields (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                value TEXT,
                confidence REAL,
                status TEXT NOT NULL,
                unit TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS field_evidence (
                id TEXT PRIMARY KEY,
                product_field_id TEXT NOT NULL,
                source_label TEXT NOT NULL,
                raw_value TEXT NOT NULL,
                extracted_at TEXT NOT NULL,
                FOREIGN KEY (product_field_id) REFERENCES product_fields(id) ON DELETE CASCADE
            );
        """)
        conn.commit()

        # Safe migrations — each is idempotent
        migrations = [
            "ALTER TABLE products ADD COLUMN canonical_hash TEXT",
            "ALTER TABLE product_fields ADD COLUMN validation_reason TEXT",
            "ALTER TABLE product_fields ADD COLUMN enrichment_method TEXT",
            "ALTER TABLE product_fields ADD COLUMN is_verified INTEGER DEFAULT 0",
            "ALTER TABLE product_fields ADD COLUMN source_fields TEXT",
            "ALTER TABLE product_fields ADD COLUMN reasoning TEXT",
        ]
        for sql in migrations:
            try:
                conn.execute(sql)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists

        # Unique index on canonical_hash for fast deduplication lookup
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_products_canonical_hash "
                "ON products(canonical_hash) WHERE canonical_hash IS NOT NULL"
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass

        conn.close()

    # ── Products ──────────────────────────────────────────────────────────

    def save_product(self, product: Product) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO products (id, name, raw_source_type, status, created_at, updated_at, canonical_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            product.id, product.name, product.raw_source_type.value,
            product.status.value, product.created_at.isoformat(),
            product.updated_at.isoformat(), product.canonical_hash
        ))
        self._conn.commit()

    def get_all_products(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM products ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_product(self, product_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM products WHERE id = ?", (product_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_product_by_canonical_hash(self, canonical_hash: str) -> Optional[dict]:
        if not canonical_hash:
            return None
        row = self._conn.execute(
            "SELECT * FROM products WHERE canonical_hash = ?", (canonical_hash,)
        ).fetchone()
        return dict(row) if row else None

    def update_product_timestamp(self, product_id: str) -> None:
        """Update a product's updated_at timestamp (called on duplicate/merge)."""
        self._conn.execute(
            "UPDATE products SET updated_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), product_id)
        )
        self._conn.commit()

    # ── Product Fields ─────────────────────────────────────────────────────

    def save_product_field(self, pf: ProductField) -> None:
        method_val = pf.enrichment_method.value if pf.enrichment_method else None
        is_ver_int = 1 if pf.is_verified else 0
        self._conn.execute("""
            INSERT OR REPLACE INTO product_fields (
                id, product_id, field_name, value, confidence, status, unit,
                enrichment_method, is_verified, source_fields, validation_reason, reasoning, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pf.id, pf.product_id, pf.field_name, pf.value,
            pf.confidence, pf.status.value, pf.unit,
            method_val, is_ver_int, pf.source_fields, pf.validation_reason, pf.reasoning,
            pf.updated_at.isoformat(),
        ))
        self._conn.commit()

    def update_product_field_validation(
        self, field_id: str, status: FieldStatus, confidence: float, reason: str, is_verified: bool = False
    ) -> None:
        """Update a field's validation status, confidence, and reason."""
        now = self._conn.execute("SELECT datetime('now')").fetchone()[0]
        is_ver_int = 1 if is_verified or status == FieldStatus.VERIFIED else 0
        self._conn.execute("""
            UPDATE product_fields
            SET status = ?, confidence = ?, validation_reason = ?, is_verified = ?, updated_at = ?
            WHERE id = ?
        """, (status.value, confidence, reason, is_ver_int, now, field_id))
        self._conn.commit()

    def get_product_fields(self, product_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM product_fields WHERE product_id = ? ORDER BY field_name ASC",
            (product_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_field_by_name(self, product_id: str, field_name: str) -> Optional[dict]:
        """Get a specific field by name for a product."""
        row = self._conn.execute(
            "SELECT * FROM product_fields WHERE product_id = ? AND field_name = ?",
            (product_id, field_name)
        ).fetchone()
        return dict(row) if row else None

    # ── Field Evidence ────────────────────────────────────────────────────

    def save_field_evidence(self, ev: FieldEvidence) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO field_evidence (id, product_field_id, source_label, raw_value, extracted_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            ev.id, ev.product_field_id, ev.source_label,
            ev.raw_value, ev.extracted_at.isoformat(),
        ))
        self._conn.commit()

    def get_field_evidence(self, product_field_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM field_evidence WHERE product_field_id = ? ORDER BY extracted_at DESC",
            (product_field_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_product_with_details(self, product_id: str) -> Optional[dict]:
        product = self.get_product(product_id)
        if not product:
            return None
        fields = self.get_product_fields(product_id)
        for f in fields:
            f["evidence"] = self.get_field_evidence(f["id"])
        product["fields"] = fields
        return product

    def get_dashboard_summary(self) -> dict[str, Any]:
        conn = self._conn
        total_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        total_fields = conn.execute("SELECT COUNT(*) FROM product_fields").fetchone()[0]

        verified_fields = conn.execute(
            "SELECT COUNT(*) FROM product_fields WHERE status = 'verified' OR is_verified = 1"
        ).fetchone()[0]
        validated_fields = conn.execute(
            "SELECT COUNT(*) FROM product_fields WHERE status = 'validated'"
        ).fetchone()[0]
        llm_enriched_fields = conn.execute("""
            SELECT COUNT(*) FROM product_fields 
            WHERE (status IN ('enriched', 'inferred') AND enrichment_method = 'llm')
               OR (status = 'enriched' AND enrichment_method = 'source_data')
        """).fetchone()[0]
        rule_inferred_fields = conn.execute("""
            SELECT COUNT(*) FROM product_fields 
            WHERE (status IN ('inferred', 'enriched') AND enrichment_method = 'deterministic_fallback')
               OR (status = 'inferred' AND (enrichment_method IS NULL OR enrichment_method = 'deterministic_fallback'))
        """).fetchone()[0]
        flagged_fields = conn.execute(
            "SELECT COUNT(*) FROM product_fields WHERE status = 'flagged'"
        ).fetchone()[0]
        conflicted_fields = conn.execute(
            "SELECT COUNT(*) FROM product_fields WHERE status = 'conflicted'"
        ).fetchone()[0]
        needs_review_fields = conn.execute("""
            SELECT COUNT(*) FROM product_fields 
            WHERE status IN ('needs_review', 'flagged', 'conflicted')
               OR (confidence IS NOT NULL AND confidence < 0.5)
        """).fetchone()[0]
        raw_fields = conn.execute(
            "SELECT COUNT(*) FROM product_fields WHERE status = 'raw'"
        ).fetchone()[0]

        needing_review = conn.execute("""
            SELECT COUNT(DISTINCT p.id) FROM products p
            LEFT JOIN product_fields pf ON p.id = pf.product_id
            WHERE p.status = 'needs_review' 
               OR pf.status IN ('conflicted', 'flagged', 'needs_review')
               OR (pf.confidence IS NOT NULL AND pf.confidence < 0.5)
        """).fetchone()[0]

        ver_pct = round((verified_fields / total_fields * 100), 1) if total_fields > 0 else 0.0
        val_pct = round((validated_fields / total_fields * 100), 1) if total_fields > 0 else 0.0
        llm_enr_pct = round((llm_enriched_fields / total_fields * 100), 1) if total_fields > 0 else 0.0
        rule_inf_pct = round((rule_inferred_fields / total_fields * 100), 1) if total_fields > 0 else 0.0
        validation_coverage = round(
            ((verified_fields + validated_fields) / total_fields * 100), 1
        ) if total_fields > 0 else 0.0

        # Pipeline stage counts (6 stages: Ingest -> Clean -> Validate -> Enrich -> Verify -> Explain)
        pipeline = {
            "ingest": total_products,
            "clean": total_fields,
            "validate": validated_fields + flagged_fields + conflicted_fields,
            "enrich": llm_enriched_fields + rule_inferred_fields,
            "verify": verified_fields + validated_fields,
            "explain": conn.execute("SELECT COUNT(*) FROM field_evidence").fetchone()[0],
        }

        return {
            "total_products": total_products,
            "total_fields": total_fields,
            "fields_verified": verified_fields,
            "fields_verified_pct": ver_pct,
            "fields_validated": validated_fields,
            "fields_validated_pct": val_pct,
            "fields_enriched": llm_enriched_fields,  # Backwards-compatible key
            "fields_enriched_pct": llm_enr_pct,
            "fields_llm_enriched": llm_enriched_fields,
            "fields_llm_enriched_pct": llm_enr_pct,
            "fields_rule_inferred": rule_inferred_fields,
            "fields_rule_inferred_pct": rule_inf_pct,
            "fields_flagged_count": flagged_fields,
            "fields_conflicted_count": conflicted_fields,
            "fields_needs_review_count": needs_review_fields,
            "fields_raw_count": raw_fields,
            "validation_coverage_pct": validation_coverage,
            "products_needing_review_count": needing_review,
            "pipeline_stages": pipeline,
        }

    # ── Catalog-Only Cleanup (safe, never touches decision tables) ─────────

    def clear_catalog_data(self) -> dict[str, int]:
        """
        Delete ALL catalog data (products, fields, evidence).
        NEVER touches decision_log, outcomes, weight_snapshots, influence_ledger.
        Returns counts of removed rows.
        """
        conn = self._conn
        ev_count = conn.execute("SELECT COUNT(*) FROM field_evidence").fetchone()[0]
        pf_count = conn.execute("SELECT COUNT(*) FROM product_fields").fetchone()[0]
        p_count  = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]

        conn.execute("DELETE FROM field_evidence")
        conn.execute("DELETE FROM product_fields")
        conn.execute("DELETE FROM products")
        conn.commit()

        return {
            "products_removed": p_count,
            "fields_removed": pf_count,
            "evidence_removed": ev_count,
        }


# Global instance
catalog_db = CatalogDatabase()
