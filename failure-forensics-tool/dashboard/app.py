"""Streamlit dashboard for browsing pipeline traces.

See SYSTEM_DESIGN.md, section 7, for the full spec:
- Read traces from SQLite + traces/{trace_id}.json
- List traces, color-coded by status (ok/flagged/failed)
- Expand a trace to see each span's step_name, status, duration, error,
  input_summary, output_summary
"""

import json
import os
import sqlite3
import sys

import streamlit as st

# dashboard/app.py sits next to src/, not inside it, and Streamlit doesn't
# reliably put the repo root on sys.path when launched as
# `streamlit run dashboard/app.py`. Add it explicitly so `from src...`
# imports work regardless of the current working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tracer import DB_PATH, TRACES_DIR, init_db  # noqa: E402

STATUS_ICON = {"OK": "🟢", "FLAGGED": "🟡", "FAILED": "🔴"}

st.set_page_config(page_title="Failure Forensics Dashboard", layout="wide")


@st.cache_data(ttl=5)
def load_traces(status_filter: str | None):
    """Query the summary rows from SQLite — this is the fast path for
    listing/filtering, so we don't have to open every JSON file just to
    render the list."""
    init_db(DB_PATH)  # safe even if it's already initialized
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        if status_filter and status_filter != "All":
            rows = conn.execute(
                """SELECT trace_id, final_status, created_at, flagged_for_eval
                   FROM traces WHERE final_status = ?
                   ORDER BY created_at DESC""",
                (status_filter,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT trace_id, final_status, created_at, flagged_for_eval
                   FROM traces ORDER BY created_at DESC"""
            ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def load_trace_detail(trace_id: str) -> dict | None:
    """Full span-by-span detail lives in the JSON file, not SQLite."""
    path = os.path.join(TRACES_DIR, f"{trace_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


st.title("🔍 Failure Forensics Dashboard")
st.caption("Every pipeline run, traced step by step — see exactly where it broke.")

col1, col2 = st.columns([1, 4])
with col1:
    status_filter = st.selectbox("Filter by status", ["All", "OK", "FLAGGED", "FAILED"])
with col2:
    if st.button("Refresh"):
        st.cache_data.clear()

traces = load_traces(status_filter)

if not traces:
    st.info(
        "No traces yet. Run the pipeline (`python -m src.pipeline` from the "
        "project root) to generate some, then hit Refresh."
    )
else:
    st.subheader(f"{len(traces)} trace(s)")

    for t in traces:
        icon = STATUS_ICON.get(t["final_status"], "⚪")
        flagged_tag = "  🚩 flagged for eval" if t["flagged_for_eval"] else ""
        label = (
            f"{icon} **{t['final_status']}** · `{t['trace_id'][:8]}…` "
            f"· {t['created_at']}{flagged_tag}"
        )

        with st.expander(label):
            detail = load_trace_detail(t["trace_id"])
            if detail is None:
                st.error("Trace JSON file is missing on disk — SQLite row exists but the detail file doesn't.")
                continue

            first_bad_name = None
            for span in detail["spans"]:
                if span["status"] in ("FAILED", "FLAGGED"):
                    first_bad_name = span["step_name"]
                    break
            if first_bad_name:
                st.warning(f"First failed step: **{first_bad_name}**")

            for span in detail["spans"]:
                span_icon = STATUS_ICON.get(span["status"], "⚪")
                duration = (
                    f"{span['duration_ms']:.1f} ms" if span["duration_ms"] is not None else "—"
                )
                st.markdown(
                    f"**{span_icon} {span['step_name']}** — `{span['status']}` — {duration}"
                )

                c1, c2 = st.columns(2)
                with c1:
                    st.caption("Input")
                    st.code(span["input_summary"] or "(empty)")
                with c2:
                    st.caption("Output")
                    st.code(span["output_summary"] or "(none)")

                if span["error"]:
                    st.error(f"Error: {span['error']}")

                st.divider()