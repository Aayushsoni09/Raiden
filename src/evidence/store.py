"""Local SQLite evidence store — structured, queryable record of each
investigation's raw tool output and computed health summary, complementing
the flat append-only audit log (src/audit) which is for human/compliance
review rather than querying.

No credentials or write capability live here; this only ever receives
data the investigator already gathered read-only.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS investigations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    report TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    hypotheses TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id INTEGER NOT NULL REFERENCES investigations(id),
    seq INTEGER NOT NULL,
    cmd TEXT,
    returncode INTEGER,
    stdout TEXT,
    stderr TEXT
);

CREATE TABLE IF NOT EXISTS health_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_id INTEGER NOT NULL REFERENCES investigations(id),
    provider TEXT,
    service TEXT,
    healthy INTEGER,
    detail TEXT
);
"""


class EvidenceStore:
    def __init__(self, db_path="audit/evidence.sqlite3"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def start_investigation(self, project, report):
        cur = self._conn.execute(
            "INSERT INTO investigations (project, report, started_at) VALUES (?, ?, ?)",
            (project, report, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid

    def record_evidence(self, investigation_id, evidence_list):
        rows = [
            (investigation_id, i, e.get("cmd"), e.get("returncode"), e.get("stdout"), e.get("stderr"))
            for i, e in enumerate(evidence_list)
        ]
        self._conn.executemany(
            "INSERT INTO evidence (investigation_id, seq, cmd, returncode, stdout, stderr) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def record_health_summary(self, investigation_id, summaries):
        def _as_int_or_none(v):
            return None if v is None else int(bool(v))

        rows = [
            (investigation_id, s.get("provider"), s.get("service"), _as_int_or_none(s.get("healthy")), s.get("detail"))
            for s in summaries
        ]
        self._conn.executemany(
            "INSERT INTO health_summary (investigation_id, provider, service, healthy, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def finish_investigation(self, investigation_id, hypotheses):
        self._conn.execute(
            "UPDATE investigations SET completed_at = ?, hypotheses = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), hypotheses, investigation_id),
        )
        self._conn.commit()

    def get_investigation(self, investigation_id):
        row = self._conn.execute(
            "SELECT id, project, report, started_at, completed_at, hypotheses FROM investigations WHERE id = ?",
            (investigation_id,),
        ).fetchone()
        if row is None:
            return None
        keys = ["id", "project", "report", "started_at", "completed_at", "hypotheses"]
        return dict(zip(keys, row))

    def list_investigations(self, project=None, limit=20):
        if project:
            rows = self._conn.execute(
                "SELECT id, project, report, started_at, completed_at FROM investigations "
                "WHERE project = ? ORDER BY id DESC LIMIT ?",
                (project, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, project, report, started_at, completed_at FROM investigations "
                "ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        keys = ["id", "project", "report", "started_at", "completed_at"]
        return [dict(zip(keys, row)) for row in rows]

    def close(self):
        self._conn.close()
