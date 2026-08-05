"""Data models for pipeline traces and spans.

See SYSTEM_DESIGN.md, section 3, for the full spec.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SpanStatus(str, Enum):
    OK = "OK"
    FAILED = "FAILED"
    FLAGGED = "FLAGGED"


@dataclass
class Span:
    step_name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    input_summary: str = ""
    output_summary: Optional[str] = None
    status: SpanStatus = SpanStatus.OK
    error: Optional[str] = None
    started_at: datetime = field(default_factory=_now)
    ended_at: Optional[datetime] = None
    duration_ms: Optional[float] = None

    def finish(self, status: SpanStatus, output_summary: Optional[str] = None,
               error: Optional[str] = None) -> None:
        self.ended_at = _now()
        self.duration_ms = (self.ended_at - self.started_at).total_seconds() * 1000
        self.status = status
        if output_summary is not None:
            self.output_summary = output_summary
        if error is not None:
            self.error = error

    def to_dict(self) -> dict:
        return {
            "step_name": self.step_name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "status": self.status.value,
            "error": self.error,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": self.duration_ms,
        }


# Worse-status wins when computing a trace's overall outcome.
_SEVERITY = {SpanStatus.OK: 0, SpanStatus.FLAGGED: 1, SpanStatus.FAILED: 2}


@dataclass
class PipelineTrace:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    spans: list[Span] = field(default_factory=list)
    final_status: SpanStatus = SpanStatus.OK
    created_at: datetime = field(default_factory=_now)

    def add_span(self, span: Span) -> None:
        self.spans.append(span)

    def compute_final_status(self) -> SpanStatus:
        """Worst-of-all-spans, not last-span-only (per SYSTEM_DESIGN.md)."""
        worst = SpanStatus.OK
        for span in self.spans:
            if _SEVERITY[span.status] > _SEVERITY[worst]:
                worst = span.status
        self.final_status = worst
        return worst

    def first_failed_step(self) -> Optional[Span]:
        """Earliest span with status FAILED or FLAGGED, in execution order."""
        for span in self.spans:
            if span.status in (SpanStatus.FAILED, SpanStatus.FLAGGED):
                return span
        return None

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "final_status": self.final_status.value,
            "created_at": self.created_at.isoformat(),
            "spans": [s.to_dict() for s in self.spans],
        }