"""
Veridex NBA Platform — Database Layer (SQLite)

Persistent storage for:
- Outcomes (human decisions + downstream results)
- Calibration records (Brier scores per bidder/decision type)
- Weight snapshots (timestamped, rollback-capable)
- Influence ledger (per-bidder influence values)
- Decision log (full decision audit trail)
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.models import (
    Outcome, CalibrationRecord, WeightSnapshot, DecisionType,
    HumanDecision, BidderType
)
from backend.config import BASE_BIDDING_WEIGHTS


DB_PATH = Path(__file__).parent.parent / "sentinel.db"


class Database:
    """Thread-safe SQLite database for persistent storage."""

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
        return self._local.conn

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = sqlite3.connect(self._db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS outcomes (
                decision_id TEXT PRIMARY KEY,
                action_id TEXT,
                human_decision TEXT NOT NULL,
                human_edit_description TEXT DEFAULT '',
                downstream_result TEXT,
                predicted_confidence REAL DEFAULT 0.0,
                was_correct INTEGER,
                recorded_at TEXT NOT NULL,
                resolved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS calibration_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bidder TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                sample_size INTEGER NOT NULL,
                brier_score REAL NOT NULL,
                computed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weight_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_type TEXT NOT NULL,
                weights TEXT NOT NULL,
                trigger TEXT NOT NULL,
                snapshot_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS influence_ledger (
                bidder TEXT PRIMARY KEY,
                influence REAL NOT NULL DEFAULT 1.0,
                total_wins INTEGER DEFAULT 0,
                total_correct INTEGER DEFAULT 0,
                total_incorrect INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS decision_log (
                decision_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                decision_type TEXT NOT NULL,
                primary_entity_id TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                recommended_action TEXT,
                human_decision TEXT,
                completed_at TEXT,
                bids_json TEXT,
                facts_json TEXT,
                progress_json TEXT,
                trace_json TEXT
            );

            CREATE TABLE IF NOT EXISTS bidding_weights (
                decision_type TEXT NOT NULL,
                bidder TEXT NOT NULL,
                weight REAL NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (decision_type, bidder)
            );
        """)
        
        # Schema migration check: add columns if they don't exist in existing database
        cursor = conn.cursor()
        for col in ["bids_json", "facts_json", "progress_json", "trace_json"]:
            try:
                cursor.execute(f"SELECT {col} FROM decision_log LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute(f"ALTER TABLE decision_log ADD COLUMN {col} TEXT")
        
        conn.commit()
        conn.close()

    # ── Outcomes ──────────────────────────────────────────────────────────

    def save_outcome(self, outcome: Outcome) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO outcomes
            (decision_id, action_id, human_decision, human_edit_description,
             downstream_result, predicted_confidence, was_correct, recorded_at, resolved_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            outcome.decision_id, outcome.action_id,
            outcome.human_decision.value, outcome.human_edit_description,
            outcome.downstream_result, outcome.predicted_confidence,
            int(outcome.was_correct) if outcome.was_correct is not None else None,
            outcome.recorded_at.isoformat(),
            outcome.resolved_at.isoformat() if outcome.resolved_at else None,
        ))
        self._conn.commit()

    def get_outcome(self, decision_id: str) -> Optional[Outcome]:
        row = self._conn.execute(
            "SELECT * FROM outcomes WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        if not row:
            return None
        return Outcome(
            decision_id=row["decision_id"],
            action_id=row["action_id"],
            human_decision=HumanDecision(row["human_decision"]),
            human_edit_description=row["human_edit_description"] or "",
            downstream_result=row["downstream_result"],
            predicted_confidence=row["predicted_confidence"],
            was_correct=bool(row["was_correct"]) if row["was_correct"] is not None else None,
            recorded_at=datetime.fromisoformat(row["recorded_at"]),
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
        )

    def get_resolved_outcomes(self, decision_type: str | None = None) -> list[Outcome]:
        """Get outcomes where was_correct is known."""
        if decision_type:
            rows = self._conn.execute("""
                SELECT o.* FROM outcomes o
                JOIN decision_log d ON o.decision_id = d.decision_id
                WHERE o.was_correct IS NOT NULL AND d.decision_type = ?
            """, (decision_type,)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM outcomes WHERE was_correct IS NOT NULL"
            ).fetchall()
        return [
            Outcome(
                decision_id=r["decision_id"],
                action_id=r["action_id"],
                human_decision=HumanDecision(r["human_decision"]),
                downstream_result=r["downstream_result"],
                predicted_confidence=r["predicted_confidence"],
                was_correct=bool(r["was_correct"]),
                recorded_at=datetime.fromisoformat(r["recorded_at"]),
                resolved_at=datetime.fromisoformat(r["resolved_at"]) if r["resolved_at"] else None,
            )
            for r in rows
        ]

    # ── Calibration Records ───────────────────────────────────────────────

    def save_calibration(self, record: CalibrationRecord) -> None:
        self._conn.execute("""
            INSERT INTO calibration_records (bidder, decision_type, sample_size, brier_score, computed_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            record.bidder, record.decision_type.value,
            record.sample_size, record.brier_score,
            record.computed_at.isoformat(),
        ))
        self._conn.commit()

    def get_calibration_records(self, bidder: str | None = None,
                                 decision_type: str | None = None) -> list[CalibrationRecord]:
        query = "SELECT * FROM calibration_records WHERE 1=1"
        params = []
        if bidder:
            query += " AND bidder = ?"
            params.append(bidder)
        if decision_type:
            query += " AND decision_type = ?"
            params.append(decision_type)
        query += " ORDER BY computed_at DESC"

        rows = self._conn.execute(query, params).fetchall()
        return [
            CalibrationRecord(
                bidder=r["bidder"],
                decision_type=DecisionType(r["decision_type"]),
                sample_size=r["sample_size"],
                brier_score=r["brier_score"],
                computed_at=datetime.fromisoformat(r["computed_at"]),
            )
            for r in rows
        ]

    # ── Weight Snapshots ──────────────────────────────────────────────────

    def save_weight_snapshot(self, snapshot: WeightSnapshot) -> None:
        self._conn.execute("""
            INSERT INTO weight_snapshots (decision_type, weights, trigger, snapshot_at)
            VALUES (?, ?, ?, ?)
        """, (
            snapshot.decision_type.value,
            json.dumps(snapshot.weights),
            snapshot.trigger,
            snapshot.snapshot_at.isoformat(),
        ))
        self._conn.commit()

    def get_weight_history(self, decision_type: str | None = None,
                            limit: int = 50) -> list[WeightSnapshot]:
        query = "SELECT * FROM weight_snapshots"
        params = []
        if decision_type:
            query += " WHERE decision_type = ?"
            params.append(decision_type)
        query += " ORDER BY snapshot_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [
            WeightSnapshot(
                decision_type=DecisionType(r["decision_type"]),
                weights=json.loads(r["weights"]),
                trigger=r["trigger"],
                snapshot_at=datetime.fromisoformat(r["snapshot_at"]),
            )
            for r in rows
        ]

    # ── Influence Ledger ──────────────────────────────────────────────────

    def get_influence(self, bidder: str) -> float:
        row = self._conn.execute(
            "SELECT influence FROM influence_ledger WHERE bidder = ?", (bidder,)
        ).fetchone()
        return row["influence"] if row else 1.0

    def get_all_influences(self) -> dict[str, float]:
        rows = self._conn.execute("SELECT bidder, influence FROM influence_ledger").fetchall()
        result = {r["bidder"]: r["influence"] for r in rows}
        # Fill defaults for missing bidders
        for b in BidderType:
            if b.value not in result:
                result[b.value] = 1.0
        return result

    def get_full_influence_ledger(self) -> dict[str, dict]:
        rows = self._conn.execute("SELECT bidder, influence, total_wins, total_correct, total_incorrect FROM influence_ledger").fetchall()
        result = {}
        for r in rows:
            result[r["bidder"]] = {
                "influence": r["influence"],
                "total_wins": r["total_wins"],
                "total_correct": r["total_correct"],
                "total_incorrect": r["total_incorrect"],
            }
        for b in BidderType:
            if b.value not in result:
                result[b.value] = {
                    "influence": 1.0,
                    "total_wins": 0,
                    "total_correct": 0,
                    "total_incorrect": 0,
                }
        return result

    def update_influence(self, bidder: str, influence: float) -> None:
        self._conn.execute("""
            INSERT INTO influence_ledger (bidder, influence, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(bidder) DO UPDATE SET influence = ?, updated_at = ?
        """, (
            bidder, influence, datetime.utcnow().isoformat(),
            influence, datetime.utcnow().isoformat(),
        ))
        self._conn.commit()

    def record_win(self, bidder: str) -> None:
        self._conn.execute("""
            UPDATE influence_ledger SET total_wins = total_wins + 1 WHERE bidder = ?
        """, (bidder,))
        self._conn.commit()

    # ── Decision Log ──────────────────────────────────────────────────────

    def log_decision(self, decision_id: str, tenant_id: str,
                      decision_type: str, primary_entity_id: str,
                      requested_by: str) -> None:
        self._conn.execute("""
            INSERT OR REPLACE INTO decision_log
            (decision_id, tenant_id, decision_type, primary_entity_id,
             requested_by, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        """, (
            decision_id, tenant_id, decision_type,
            primary_entity_id, requested_by,
            datetime.utcnow().isoformat(),
        ))
        self._conn.commit()

    def update_decision_status(self, decision_id: str, status: str,
                                 recommended_action: str = "",
                                 human_decision: str = "") -> None:
        updates = ["status = ?"]
        params = [status]
        if recommended_action:
            updates.append("recommended_action = ?")
            params.append(recommended_action)
        if human_decision:
            updates.append("human_decision = ?")
            params.append(human_decision)
        if status in ("completed", "rejected"):
            updates.append("completed_at = ?")
            params.append(datetime.utcnow().isoformat())

        params.append(decision_id)
        self._conn.execute(
            f"UPDATE decision_log SET {', '.join(updates)} WHERE decision_id = ?",
            params
        )
        self._conn.commit()

    def save_decision_state_json(self, decision_id: str, bids_json: str, facts_json: str, progress_json: str, trace_json: str) -> None:
        self._conn.execute("""
            UPDATE decision_log
            SET bids_json = ?, facts_json = ?, progress_json = ?, trace_json = ?
            WHERE decision_id = ?
        """, (bids_json, facts_json, progress_json, trace_json, decision_id))
        self._conn.commit()

    def get_pending_decisions(self, tenant_id: str | None = None) -> list[dict]:
        query = "SELECT * FROM decision_log WHERE status = 'pending'"
        params = []
        if tenant_id:
            query += " AND tenant_id = ?"
            params.append(tenant_id)
        query += " ORDER BY created_at DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_all_decisions(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM decision_log ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def find_active_decision(self, decision_type: str, primary_entity_id: str) -> dict | None:
        """Find an existing unresolved decision for the same entity + decision_type.

        Terminal statuses (completed, rejected) are excluded — only pending,
        awaiting_review, and blocked decisions are considered active.
        """
        row = self._conn.execute(
            """SELECT * FROM decision_log
               WHERE decision_type = ? AND primary_entity_id = ?
                 AND status NOT IN ('completed', 'rejected')
               ORDER BY created_at DESC LIMIT 1""",
            (decision_type, primary_entity_id),
        ).fetchone()
        return dict(row) if row else None

    def delete_all_decisions(self) -> int:
        """Delete all rows from decision_log. Returns count deleted."""
        count = self._conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]
        self._conn.execute("DELETE FROM decision_log")
        self._conn.commit()
        return count

    def delete_all_outcomes(self) -> int:
        """Delete all rows from outcomes. Returns count deleted."""
        count = self._conn.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
        self._conn.execute("DELETE FROM outcomes")
        self._conn.commit()
        return count

    # ── Bidding Weights ───────────────────────────────────────────────────

    def get_bidding_weights(self, decision_type: str) -> dict[str, float]:
        """Get current bidding weights for a decision type, falling back to base weights."""
        rows = self._conn.execute(
            "SELECT bidder, weight FROM bidding_weights WHERE decision_type = ?",
            (decision_type,)
        ).fetchall()
        if rows:
            return {r["bidder"]: r["weight"] for r in rows}
        return dict(BASE_BIDDING_WEIGHTS)

    def update_bidding_weight(self, decision_type: str, bidder: str, weight: float) -> None:
        self._conn.execute("""
            INSERT INTO bidding_weights (decision_type, bidder, weight, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(decision_type, bidder) DO UPDATE SET weight = ?, updated_at = ?
        """, (
            decision_type, bidder, weight, datetime.utcnow().isoformat(),
            weight, datetime.utcnow().isoformat(),
        ))
        self._conn.commit()


# Global instance
db = Database()
