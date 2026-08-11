"""4-step pipeline: ingestion -> extraction -> classification -> generation

See SYSTEM_DESIGN.md, section 4, for the full spec.
"""

from __future__ import annotations

from .tracer import Tracer


def ingest(document: str, tracer: Tracer):
    with tracer.step("ingest", input_summary=document[:80]) as span:
        cleaned = document.strip()
        if not cleaned:
            # Leave output_summary unset on purpose — the tracer treats
            # a step that finishes without an output as a silent failure
            # and marks it FLAGGED. This is how empty input gets caught
            # instead of quietly sailing through the pipeline.
            return None
        span.output_summary = f"{len(cleaned)} chars"
        return cleaned


def extract(document: str, tracer: Tracer):
    with tracer.step("extract", input_summary=document[:80]) as span:
        # Stand-in for an LLM call — pulls simple "entities" out of the text.
        entities = {"length": len(document), "preview": document[:40]}
        span.output_summary = f"extracted {len(entities)} fields"
        return entities


def classify(entities: dict, tracer: Tracer):
    with tracer.step("classify", input_summary=str(entities)[:80]) as span:
        preview = entities.get("preview", "").lower()
        category = "report" if "revenue" in preview else "general"
        span.output_summary = f"category={category}"
        return category


def generate(category: str, entities: dict, tracer: Tracer):
    with tracer.step("generate", input_summary=category) as span:
        response = f"Document classified as '{category}'."
        span.output_summary = response[:80]
        return response


def run_pipeline(document: str):
    """Runs all 4 steps, always saves the trace (even on failure), and
    returns (output, trace)."""
    tracer = Tracer()
    try:
        cleaned = ingest(document, tracer)
        # If ingest flagged empty input, fall back to the raw document
        # so extract still has something (a string) to work with.
        working_doc = cleaned if cleaned is not None else document
        entities = extract(working_doc, tracer)
        category = classify(entities, tracer)
        output = generate(category, entities, tracer)
    finally:
        tracer.save()
    return output, tracer.trace

