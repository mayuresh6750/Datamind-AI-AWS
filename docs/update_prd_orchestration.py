"""
Update PRD docx to reflect actual Phase 1 orchestration (tasks.py + BackgroundTasks).

Word splits text across multiple <w:t> runs, so replacements must be applied
per-paragraph after joining run text. See docs/LangGraph-Orchestration-Analysis.md.
"""

from __future__ import annotations

import os
import re
import zipfile

# Update the file the user is viewing locally
INPUT = "DataMind_AI_PRD_Phase1_Orchestration.docx"
OUTPUT = "DataMind_AI_PRD_Phase1_Orchestration.docx"
FALLBACK_INPUT = "DataMind_AI_PRD_updated.docx"

# Longer phrases first. Phase 1 must NOT list LangGraph as active orchestration.
REPLACEMENTS: list[tuple[str, str]] = [
    (
        "LangGraph (supervisor pattern), Pydantic-validated outputs",
        "FastAPI BackgroundTasks + backend/app/workers/tasks.py, Pydantic-validated outputs",
    ),
    (
        "Multi-agent pipeline coordination, state machine, retry, HITL gates",
        "Imperative async pipeline in tasks.py; agents called directly; HITL via HTTP + dataset.status",
    ),
    (
        "DataMind uses a supervisor-agent pattern coordinated by LangGraph. A supervisor agent receives a job, decomposes it into a sequence of specialised steps, delegates to sub-agents, validates their structured outputs, decides what to do on failure, and pauses at human-in-the-loop checkpoints to wait for user decisions.",
        "DataMind uses a multi-agent pipeline. Phase 1 orchestration is imperative: FastAPI BackgroundTasks dispatch async functions in backend/app/workers/tasks.py (there is no async.py). Each stage calls its agent directly. The file backend/app/agents/supervisor.py contains a Phase 2 orchestration scaffold that is not invoked in production. HITL gates pause between stages via HTTP endpoints and dataset.status persisted in Postgres.",
    ),
    (
        "Shared LangGraph state object holds the pipeline state: dataset_id, raw_uris, current parquet_uri, profile_json, merge_plan, cleaning_plan, hitl_decisions, audit log, accumulated confidence.",
        "Pipeline state between stages is persisted via Postgres (datasets, hitl_decisions, pipeline_runs) and Supabase Storage (archive/json URIs). Each tasks.py function re-loads state from DB/storage on entry. There is no shared graph state object in Phase 1.",
    ),
    (
        "Agentic frameworks (LangGraph, function-calling models) are mature enough to coordinate multi-step data tasks reliably while pausing for human approval at well-defined checkpoints.",
        "Agentic frameworks and function-calling models are mature enough to coordinate multi-step data tasks reliably while pausing for human approval at well-defined checkpoints. DataMind Phase 1 uses FastAPI BackgroundTasks and tasks.py; graph-based orchestration is deferred to Phase 2.",
    ),
    (
        "Agent orchestration (LangGraph, structured tool-use APIs) made it feasible",
        "Agent orchestration (structured tool-use APIs and imperative task pipelines) made it feasible",
    ),
    # Shorter fallbacks when Word splits or shortens text
    (
        "LangGraph state machine",
        "tasks.py async pipeline (Phase 1); supervisor.py scaffold (Phase 2, not wired)",
    ),
    (
        "coordinated by LangGraph",
        "orchestrated in Phase 1 by tasks.py (BackgroundTasks)",
    ),
    (
        "Shared LangGraph state object holds",
        "Pipeline state in Postgres/Storage holds",
    ),
    (
        ", LangGraph,",
        ", langgraph library (Phase 2 scaffold only; not used in Phase 1),",
    ),
    (
        "(LangGraph, function-calling models)",
        "(function-calling models and multi-agent pipelines)",
    ),
]


def _extract_wp_text(wp_xml: str) -> str:
    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", wp_xml))


def _set_wp_text(wp_xml: str, new_text: str) -> str:
    first = True

    def _repl(match: re.Match[str]) -> str:
        nonlocal first
        if first:
            first = False
            return f"{match.group(1)}{new_text}{match.group(3)}"
        return f"{match.group(1)}{match.group(3)}"

    return re.sub(r"(<w:t[^>]*>)([^<]*)(</w:t>)", _repl, wp_xml)


def _apply_replacements(text: str) -> str:
    updated = text
    for old, new in REPLACEMENTS:
        updated = updated.replace(old, new)
    return updated


def process_document_xml(xml: str) -> tuple[str, int]:
    changes = 0

    def _process_wp(match: re.Match[str]) -> str:
        nonlocal changes
        wp = match.group(0)
        original = _extract_wp_text(wp)
        updated = _apply_replacements(original)
        if updated != original:
            changes += 1
            return _set_wp_text(wp, updated)
        return wp

    processed = re.sub(r"<w:p\b[^>]*>.*?</w:p>", _process_wp, xml, flags=re.DOTALL)
    for old, new in REPLACEMENTS:
        if old in processed:
            processed = processed.replace(old, new)
            changes += 1
    return processed, changes


def verify_docx(path: str) -> None:
    with zipfile.ZipFile(path, "r") as z:
        plain = re.sub(r"<[^>]+>", " ", z.read("word/document.xml").decode("utf-8"))
        plain = re.sub(r"\s+", " ", plain)
    bad_phrases = [
        "LangGraph (supervisor pattern)",
        "coordinated by LangGraph",
        "Shared LangGraph state",
        "LangGraph state machine",
    ]
    print(f"\nVerification for {path}:")
    print(f"  tasks.py mentions: {plain.count('tasks.py')}")
    print(f"  BackgroundTasks mentions: {plain.count('BackgroundTasks')}")
    print(f"  Total 'LangGraph' count: {plain.count('LangGraph')}")
    for phrase in bad_phrases:
        count = plain.count(phrase)
        status = "OK" if count == 0 else f"STILL PRESENT ({count})"
        print(f"  {phrase}: {status}")


def main() -> None:
    source = INPUT if os.path.exists(INPUT) else FALLBACK_INPUT
    if not os.path.exists(source):
        raise SystemExit(f"No input docx found: {INPUT} or {FALLBACK_INPUT}")

    all_files: dict[str, bytes] = {}
    with zipfile.ZipFile(source, "r") as zin:
        for name in zin.namelist():
            all_files[name] = zin.read(name)

    doc_xml = all_files["word/document.xml"].decode("utf-8")
    doc_xml, changes = process_document_xml(doc_xml)
    all_files["word/document.xml"] = doc_xml.encode("utf-8")

    tmp = OUTPUT + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in all_files.items():
            zout.writestr(name, data)
    os.replace(tmp, OUTPUT)

    print(f"Source: {source}")
    print(f"Saved: {OUTPUT}")
    print(f"Paragraph-level changes: {changes}")
    verify_docx(OUTPUT)


if __name__ == "__main__":
    main()
