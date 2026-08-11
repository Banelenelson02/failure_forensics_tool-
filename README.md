# Failure Forensics Tool for AI Pipelines

## Overview
An observability layer for multi-step AI pipelines that traces every intermediate step. It identifies exactly where failures originate when the final output is bad and feeds flagged failures back into a growing evaluation dataset.

## Why This Project Exists
When a complex AI pipeline produces bad results, most teams have no idea which step broke. This project solves that by providing full tracing and observability, showcasing senior-level engineering skills.

See SYSTEM_DESIGN.md for the full architecture, data flow, and what each file needs to do.

## Pipeline Architecture
1. Ingestion — Parses raw text and simulated documents.
2. Extraction — Uses an LLM to pull structured entities.
3. Classification — Categorizes the document based on context.
4. Generation — Creates a tailored response.

## Tech Stack
| Component | Tool / Library |
|---|---|
| Language | Python 3.11+ |
| Pipeline Framework | Custom Python orchestration |
| LLM Provider | OpenAI API |
| Tracing | OpenTelemetry |
| Storage | SQLite + JSON trace files |
| Visualization | Streamlit |
| Feedback Loop | FastAPI REST API |
| Containerization | Docker |

## Roadmap
- [ ] Phase 1: models.py — data shapes
- [ ] Phase 2: tracer.py — span capture + SQLite/JSON persistence
- [ ] Phase 3: pipeline.py — 4-step pipeline wired to the tracer
- [ ] Phase 4: tests/test_pipeline.py
- [ ] Phase 5: feedback_api.py
- [ ] Phase 6: dashboard/app.py
- [ ] Phase 7 (later): integrate tracing into the SA Grocery Price Intelligence Platform Airflow DAG
