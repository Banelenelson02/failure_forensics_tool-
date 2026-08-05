"""Tests for the pipeline + tracer.

See SYSTEM_DESIGN.md, section 8:
- a normal run produces all 4 spans in order
- a bad input (e.g. empty string) gets flagged somewhere, not silently
  passed through
- (section 5) if a step raises partway through, later steps do not run
"""

import json

import pytest

from src.models import SpanStatus
from src.pipeline import run_pipeline
from src import pipeline as pipeline_module


@pytest.fixture(autouse=True)
def isolated_traces_dir(tmp_path, monkeypatch):
    """run_pipeline() builds a Tracer with default paths ('traces/...'),
    so run every test from a scratch tmp directory instead of polluting
    the real repo's traces/ folder."""
    monkeypatch.chdir(tmp_path)


def test_pipeline_runs_and_traces_all_steps():
    """A normal run should produce exactly 4 spans, in the right order,
    all OK, with the trace's overall status also OK."""
    output, trace = run_pipeline(
        "The quarterly report shows strong revenue growth in the enterprise segment."
    )

    assert output is not None

    step_names = [span.step_name for span in trace.spans]
    assert step_names == ["ingest", "extract", "classify", "generate"]

    assert all(span.status == SpanStatus.OK for span in trace.spans)
    assert trace.final_status == SpanStatus.OK
    assert trace.first_failed_step() is None

    json_path = tmp_path_json(trace)
    assert json_path.exists()
    with open(json_path) as f:
        saved = json.load(f)
    assert saved["trace_id"] == trace.trace_id
    assert len(saved["spans"]) == 4


def test_empty_input_is_flagged_not_silently_passed():
    """Empty input must not silently produce an 'OK' trace — it should
    surface as a FLAGGED (or FAILED) span, found by first_failed_step()."""
    output, trace = run_pipeline("")

    assert trace.final_status in (SpanStatus.FLAGGED, SpanStatus.FAILED)

    first_bad = trace.first_failed_step()
    assert first_bad is not None
    assert first_bad.status in (SpanStatus.FLAGGED, SpanStatus.FAILED)
    assert first_bad.step_name == "ingest"


def test_step_failure_halts_pipeline(monkeypatch):
    """If a step raises, later steps must not run, and the trace up to
    the failure must still be saved (not lost)."""

    def boom(document, tracer):
        with tracer.step("extract", input_summary=document[:80]):
            raise ValueError("simulated extraction failure")

    monkeypatch.setattr(pipeline_module, "extract", boom)

    with pytest.raises(ValueError):
        pipeline_module.run_pipeline("some input text")

    trace_files = list((tmp_path_traces_dir()).glob("*.json"))
    assert len(trace_files) == 1
    with open(trace_files[0]) as f:
        saved = json.load(f)

    step_names = [s["step_name"] for s in saved["spans"]]
    assert step_names == ["ingest", "extract"]
    assert saved["spans"][-1]["status"] == "FAILED"
    assert saved["final_status"] == "FAILED"


# --- small helpers -----------------------------------------------------

def tmp_path_traces_dir():
    from pathlib import Path
    return Path("traces")


def tmp_path_json(trace):
    return tmp_path_traces_dir() / f"{trace.trace_id}.json"