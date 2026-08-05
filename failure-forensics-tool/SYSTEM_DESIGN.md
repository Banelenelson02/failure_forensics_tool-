# System Design — Failure Forensics Tool

## 1. Data flow
input text -> [ingestion] -> [extraction] -> [classification] -> [generation] -> output
Each step wrapped in a span -> spans collected into a PipelineTrace -> saved to SQLite + JSON.

## 2. src/models.py
- SpanStatus enum: OK, FAILED, FLAGGED
- Span: step_name, trace_id, span_id, input_summary, output_summary, status, error, started_at, ended_at, duration_ms
- PipelineTrace: trace_id, spans, final_status, created_at
- PipelineTrace.first_failed_step() -> earliest FAILED/FLAGGED span
- Design question: final_status should be worst-of-all-spans, not last-span-only.

## 3. src/tracer.py
- init_db() -> creates traces/traces.db with `traces` and `spans` tables
- Tracer class holding one PipelineTrace per run
- Tracer.step(step_name, input_summary) context manager:
  - creates a Span, times it
  - catches exceptions -> FAILED, records error, re-raises
  - no output set -> FLAGGED
  - wrap in an OpenTelemetry span too
- Tracer.save() -> computes final_status, writes traces/{trace_id}.json, inserts SQLite rows

## 4. src/pipeline.py
- ingest(text, tracer), extract(document, tracer), classify(entities, tracer), generate(category, tracer)
- each wraps its work in tracer.step(...), sets span.output_summary
- run_pipeline(text) -> (output, trace): one Tracer, all 4 steps, tracer.save() even on failure
- stub extraction/generation logic until tracing is proven, then swap in real OpenAI calls

## 5. src/feedback_api.py
- GET /traces (optional ?status= filter)
- GET /traces/{trace_id}
- POST /traces/{trace_id}/flag -> sets flagged_for_eval=True in the JSON

## 6. dashboard/app.py
- Streamlit: read SQLite + traces/{trace_id}.json
- list traces color-coded by status, expandable per-span detail

## 7. tests/test_pipeline.py
- test_pipeline_runs_and_traces_all_steps -> 4 spans, correct order
- test_empty_input_is_flagged_not_silently_passed -> bad input surfaces as FAILED/FLAGGED

## 8. Later: integrate into Grocery Price Intelligence
Wrap the real Airflow DAG (scrape -> clean -> load -> geocode -> recommend) with the
same Tracer/Span models instead of this toy pipeline. Don't build this yet.

## Build order
1. models.py  2. tracer.py  3. pipeline.py  4. tests  5. feedback_api.py  6. dashboard/app.py
