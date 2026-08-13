"""Wraps pipeline steps in spans, persists traces to SQLite + JSON files.

See SYSTEM_DESIGN.md, section 4, for the full spec:
- init_db() — creates traces/traces.db with `traces` and `spans` tables
- Tracer class — holds one PipelineTrace per run
- Tracer.step(step_name, input_summary) — context manager: creates a Span,
  times it, catches exceptions -> FAILED, empty output -> FLAGGED, appends
  to the trace. Wraps the underlying work in an OpenTelemetry span too.
- Tracer.save() — computes final_status, writes traces/{trace_id}.json,
  and inserts rows into SQLite
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3

from .models import PipelineTrace, Span, SpanStatus

try:
    from opentelemetry import trace as otel_trace
    _otel_tracer = otel_trace.get_tracer(__name__)
except ImportError:
    _otel_tracer = None

TRACES_DIR = "traces"
DB_PATH = os.path.join(TRACES_DIR, "traces.db")


def init_db(db_path: str = DB_PATH) -> None:
    """Create traces.db with `traces` and `spans` tables if they don't exist."""
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS traces (
                                                  trace_id TEXT PRIMARY KEY,
                                                  final_status TEXT,
                                                  created_at TEXT,
                                                  flagged_for_eval INTEGER DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS spans (
                                                 span_id TEXT PRIMARY KEY,
                                                 trace_id TEXT,
                                                 step_name TEXT,
                                                 input_summary TEXT,
                                                 output_summary TEXT,
                                                 status TEXT,
                                                 error TEXT,
                                                 started_at TEXT,
                                                 ended_at TEXT,
                                                 duration_ms REAL,
                                                 FOREIGN KEY (trace_id) REFERENCES traces (trace_id)
                )
            """
        )
        conn.commit()
    finally:
        conn.close()


class Tracer:
    """One instance per pipeline run. Wraps each step in a Span and persists
    the resulting PipelineTrace to SQLite + a JSON file on save()."""

    def __init__(self, traces_dir: str = TRACES_DIR, db_path: str = DB_PATH):
        self.trace = PipelineTrace()
        self.traces_dir = traces_dir
        self.db_path = db_path
        init_db(db_path)

    @contextlib.contextmanager
    def step(self, step_name: str, input_summary: str = ""):
        """Context manager for one pipeline step.

        Usage:
            with tracer.step("extract", input_summary=doc[:80]) as span:
                result = do_work(doc)
                span.output_summary = summarize(result)

        - Exception raised inside -> span marked FAILED, error recorded,
          exception re-raised (so the pipeline still stops).
        - Completes but never sets span.output_summary -> marked FLAGGED
          (this is the silent-failure detector).
        - Otherwise -> marked OK.
        Either way, the finished span is appended to the trace.
        """
        span = Span(
            step_name=step_name,
            trace_id=self.trace.trace_id,
            input_summary=input_summary,
        )

        otel_cm = (
            _otel_tracer.start_as_current_span(step_name)
            if _otel_tracer is not None
            else contextlib.nullcontext()
        )

        with otel_cm:
            try:
                yield span
            except Exception as e:
                span.finish(SpanStatus.FAILED, error=str(e))
                self.trace.add_span(span)
                raise
            else:
                if span.output_summary is None:
                    span.finish(
                        SpanStatus.FLAGGED,
                        error="Step completed without setting output_summary",
                    )
                else:
                    span.finish(SpanStatus.OK)
                self.trace.add_span(span)

    def save(self) -> None:
        """Compute final_status, then persist to JSON and SQLite. Safe to
        call even after a step raised (the raised spans are already in
        self.trace by the time the exception propagates)."""
        self.trace.compute_final_status()
        os.makedirs(self.traces_dir, exist_ok=True)

        json_path = os.path.join(self.traces_dir, f"{self.trace.trace_id}.json")
        with open(json_path, "w") as f:
            json.dump(self.trace.to_dict(), f, indent=2)

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT OR REPLACE INTO traces
                   (trace_id, final_status, created_at) VALUES (?, ?, ?)""",
                (
                    self.trace.trace_id,
                    self.trace.final_status.value,
                    self.trace.created_at.isoformat(),
                ),
            )
            for span in self.trace.spans:
                conn.execute(
                    """INSERT OR REPLACE INTO spans
                       (span_id, trace_id, step_name, input_summary,
                        output_summary, status, error, started_at,
                        ended_at, duration_ms)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        span.span_id,
                        span.trace_id,
                        span.step_name,
                        span.input_summary,
                        span.output_summary,
                        span.status.value,
                        span.error,
                        span.started_at.isoformat(),
                        span.ended_at.isoformat() if span.ended_at else None,
                        span.duration_ms,
                    ),
                )
            conn.commit()
        finally:
            conn.close()