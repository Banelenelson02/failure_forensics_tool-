"""REST API for browsing traces and flagging failures into an eval dataset.

See SYSTEM_DESIGN.md, section 6, for the full spec:
- GET  /traces               — list traces from SQLite, optional ?status= filter
- GET  /traces/{trace_id}    — full JSON detail for one trace
- POST /traces/{trace_id}/flag — mark a trace flagged_for_eval=True

Flagged traces are the seed of the growing evaluation dataset the brief
calls for: every trace a human marks here becomes a candidate eval case.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from .tracer import DB_PATH, TRACES_DIR, init_db

app = FastAPI(title="Failure Forensics Feedback API")

# I should makee sure the DB + tables exist even if the API is started before any
# pipeline run has happened, so /traces returns an empty list instead of
# a 500.
init_db(DB_PATH)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _trace_json_path(trace_id: str) -> str:
    return os.path.join(TRACES_DIR, f"{trace_id}.json")


@app.get("/traces")
def list_traces(
    status: Optional[str] = Query(
        default=None,
        description="Filter by final_status: 'ok', 'flagged', or 'failed' (case-insensitive)",
    )
):
    """List traces from SQLite, most recent first. Optional ?status= filter."""
    conn = _get_conn()
    try:
        if status:
            rows = conn.execute(
                """SELECT trace_id, final_status, created_at, flagged_for_eval
                   FROM traces WHERE final_status = ?[]
                   ORDER BY created_at DESC""",
                (status.upper(),),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT trace_id, final_status, created_at, flagged_for_eval
                   FROM traces ORDER BY created_at DESC"""
            ).fetchall()
    finally:
        conn.close()

    return [
        {
            "trace_id": row["trace_id"],
            "final_status": row["final_status"],
            "created_at": row["created_at"],
            "flagged_for_eval": bool(row["flagged_for_eval"]),
        }
        for row in rows
    ]


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str):
    """Full JSON detail for one trace — every span's input/output/error/timing."""
    path = _trace_json_path(trace_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"trace '{trace_id}' not found")
    with open(path) as f:
        return json.load(f)


@app.post("/traces/{trace_id}/flag")
def flag_trace(trace_id: str):
    """Mark a trace as flagged_for_eval — both in its JSON file (source of
    truth for full detail) and in SQLite (source of truth for fast listing/
    filtering), so the two never drift apart."""
    path = _trace_json_path(trace_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"trace '{trace_id}' not found")

    with open(path) as f:
        data = json.load(f)
    data["flagged_for_eval"] = True
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

    conn = _get_conn()
    try:
        cursor = conn.execute(
            "UPDATE traces SET flagged_for_eval = 1 WHERE trace_id = ?", (trace_id,)
        )
        conn.commit()
        if cursor.rowcount == 0:
            # JSON file existed but the SQLite row didn't ,it shouldn't happen
            # in normal operation, but don't silently pretend it worked.
            raise HTTPException(
                status_code=500,
                detail=f"trace '{trace_id}' found in JSON but missing from SQLite",
            )
    finally:
        conn.close()

    return {"trace_id": trace_id, "flagged_for_eval": True}

