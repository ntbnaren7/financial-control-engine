import sqlite3
import json
from datetime import datetime, timezone
from typing import List, Optional

from src.domain.evidence.models import Evidence

class EvidenceRepository:
    def __init__(self, db_path: str = "sqlite.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS evidence (
                    evidence_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    evidence_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    provenance TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_source_entity ON evidence (source, entity_id)")

    def save(self, evidence: Evidence) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO evidence 
                (evidence_id, source, entity_id, timestamp, evidence_type, payload, provenance) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence.evidence_id,
                    evidence.source,
                    evidence.entity_id,
                    evidence.timestamp.isoformat(),
                    evidence.evidence_type,
                    json.dumps(evidence.payload),
                    json.dumps(evidence.provenance)
                )
            )

    def get_by_id(self, evidence_id: str) -> Optional[Evidence]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM evidence WHERE evidence_id = ?", (evidence_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_evidence(row)

    def get_all(self) -> List[Evidence]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT * FROM evidence ORDER BY timestamp ASC")
            return [self._row_to_evidence(row) for row in cursor.fetchall()]

    def _row_to_evidence(self, row) -> Evidence:
        return Evidence(
            evidence_id=row[0],
            source=row[1],
            entity_id=row[2],
            timestamp=datetime.fromisoformat(row[3]),
            evidence_type=row[4],
            payload=json.loads(row[5]),
            provenance=json.loads(row[6])
        )

# Stubs for Correlation and Case Repositories, we will flesh them out when those models are created
class CorrelationRepository:
    def __init__(self, db_path: str = "sqlite.db"):
        self.db_path = db_path
        pass

class CaseRepository:
    def __init__(self, db_path: str = "sqlite.db"):
        self.db_path = db_path
        pass
