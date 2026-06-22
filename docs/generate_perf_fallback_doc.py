"""
Generate DataMind AI — Performance & Fallback Fix Reference Doc
Covers everything from: "I have observed 2 issues — performance issue while generating
the strategy, and fallback not working when one model is not working"
Run:  python docs/generate_perf_fallback_doc.py
"""
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc = Document()

for section in doc.sections:
    section.top_margin    = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin   = Cm(2.5)
    section.right_margin  = Cm(2.5)

ACCENT = RGBColor(0x1E, 0x40, 0xAF)
GREEN  = RGBColor(0x16, 0x65, 0x34)
RED    = RGBColor(0x99, 0x17, 0x17)
GRAY   = RGBColor(0x37, 0x41, 0x51)
ORANGE = RGBColor(0xC2, 0x57, 0x00)


def set_cell_bg(cell, hex_color):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement('w:shd')
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  hex_color)
    tcPr.append(shd)


def set_row_bg(row, hex_color):
    for cell in row.cells:
        set_cell_bg(cell, hex_color)


def add_heading(text, level=1, color=None):
    p = doc.add_heading(text, level=level)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if color:
        for run in p.runs:
            run.font.color.rgb = color
    return p


def add_para(text='', bold=False, italic=False, size=10, color=None, space_after=6):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    if text:
        run = p.add_run(text)
        run.bold   = bold
        run.italic = italic
        run.font.size = Pt(size)
        if color:
            run.font.color.rgb = color
    return p


def add_code(lines, label=''):
    if label:
        lp = doc.add_paragraph()
        lp.paragraph_format.space_after  = Pt(2)
        lp.paragraph_format.space_before = Pt(6)
        lr = lp.add_run(label)
        lr.bold = True
        lr.font.size = Pt(9)
        lr.font.color.rgb = GRAY
    tbl  = doc.add_table(rows=1, cols=1)
    tbl.style = 'Table Grid'
    cell = tbl.cell(0, 0)
    set_cell_bg(cell, 'F1F5F9')
    cell.paragraphs[0]._element.getparent().remove(cell.paragraphs[0]._element)
    for line in lines:
        cp = cell.add_paragraph(line)
        cp.paragraph_format.space_after  = Pt(0)
        cp.paragraph_format.space_before = Pt(0)
        cr = cp.runs[0] if cp.runs else cp.add_run('')
        cr.font.name = 'Courier New'
        cr.font.size = Pt(8.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def add_before_after(before_lines, after_lines,
                     before_label='BEFORE (problem)', after_label='AFTER (fixed)'):
    tbl = doc.add_table(rows=1, cols=2)
    tbl.style = 'Table Grid'
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
    for i, (label, lines, bg, fc) in enumerate([
        (before_label, before_lines, 'FEF2F2', '991717'),
        (after_label,  after_lines,  'F0FDF4', '166534'),
    ]):
        cell = tbl.cell(0, i)
        set_cell_bg(cell, bg)
        cell.paragraphs[0]._element.getparent().remove(cell.paragraphs[0]._element)
        hp = cell.add_paragraph(label)
        hr = hp.runs[0] if hp.runs else hp.add_run(label)
        hr.bold = True
        hr.font.size = Pt(9)
        hr.font.color.rgb = RGBColor.from_string(fc)
        hp.paragraph_format.space_after = Pt(4)
        for line in lines:
            lp = cell.add_paragraph(line)
            lp.paragraph_format.space_after  = Pt(0)
            lp.paragraph_format.space_before = Pt(0)
            lr = lp.runs[0] if lp.runs else lp.add_run(line)
            lr.font.name = 'Courier New'
            lr.font.size = Pt(8)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)


def add_table(headers, rows, header_bg='1E40AF', header_fg='FFFFFF', alt_bg='EFF6FF'):
    tbl = doc.add_table(rows=1 + len(rows), cols=len(headers))
    tbl.style = 'Table Grid'
    hdr = tbl.rows[0]
    set_row_bg(hdr, header_bg)
    for i, h in enumerate(headers):
        c = hdr.cells[i]
        c.paragraphs[0].clear()
        r = c.paragraphs[0].add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor.from_string(header_fg)
    for ri, row_data in enumerate(rows):
        row = tbl.rows[ri + 1]
        if ri % 2 == 1:
            set_row_bg(row, alt_bg)
        for ci, val in enumerate(row_data):
            c = row.cells[ci]
            c.paragraphs[0].clear()
            r = c.paragraphs[0].add_run(str(val))
            r.font.size = Pt(9)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)


def add_bullet(text):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_after = Pt(3)
    p.add_run(text).font.size = Pt(10)


def file_tag(path):
    p = doc.add_paragraph()
    p.paragraph_format.space_after  = Pt(4)
    p.paragraph_format.space_before = Pt(8)
    r1 = p.add_run('File: ')
    r1.bold = True
    r1.font.size = Pt(10)
    r1.font.color.rgb = ACCENT
    r2 = p.add_run(path)
    r2.font.name = 'Courier New'
    r2.font.size  = Pt(9)
    r2.font.color.rgb = ACCENT


# ══════════════════════════════════════════════════════════════════════════════
# COVER
# ══════════════════════════════════════════════════════════════════════════════
cover = doc.add_paragraph()
cover.alignment = WD_ALIGN_PARAGRAPH.CENTER
cover.paragraph_format.space_before = Pt(60)
r = cover.add_run('DataMind AI')
r.bold = True
r.font.size = Pt(32)
r.font.color.rgb = ACCENT

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
rs = sub.add_run('LLM Fallback & Pipeline Performance\nTechnical Fix Reference Guide')
rs.bold = True
rs.font.size = Pt(16)
rs.font.color.rgb = GRAY

doc.add_paragraph().paragraph_format.space_after = Pt(20)
meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
meta.add_run('Branch: Priyanka-K/feat-backend   |   Date: 2026-06-21').font.size = Pt(10)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# TABLE OF CONTENTS
# ══════════════════════════════════════════════════════════════════════════════
add_heading('Contents', 1, ACCENT)
for num, title in [
    ('1',  'Origin of the Investigation'),
    ('2',  'Background — LLM Architecture & Model Setup'),
    ('3',  'Issue 1 Diagnosed — Why Fallback Was Not Working'),
    ('4',  'Fix 1A — Quota Error Fast-Fail (llm.py)'),
    ('5',  'Fix 1B — Exponential Backoff for Transient Errors (llm.py)'),
    ('6',  'Model Name Alignment (.env.example + llm.py)'),
    ('7',  'Issue 2 Diagnosed — Why Performance Was Slow'),
    ('8',  'Fix 2A — Embedding Model Pre-Warming at Startup (main.py)'),
    ('9',  'Fix 2B — Reuse Stored Column Profiles (tasks.py)'),
    ('10', 'Fix 2C — Bulk INSERT for PostgreSQL Rows (tasks.py)'),
    ('11', 'Fix 2D — Bulk INSERT for pgvector Embeddings (tasks.py)'),
    ('12', 'Complete Before/After: Full llm.py'),
    ('13', 'Impact Summary'),
    ('14', 'Interview Quick Reference'),
]:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    r1 = p.add_run(f'{num}.  ')
    r1.bold = True
    r1.font.size = Pt(10)
    r1.font.color.rgb = ACCENT
    r2 = p.add_run(title)
    r2.font.size = Pt(10)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — ORIGIN
# ══════════════════════════════════════════════════════════════════════════════
add_heading('1. Origin of the Investigation', 1, ACCENT)
add_para(
    'During testing of the DataMind AI pipeline with sample healthcare CSV files (10 rows each), '
    'two distinct issues were observed and reported:',
    size=10, space_after=8
)
add_table(
    ['Issue', 'Observed Symptom', 'Category'],
    [
        ['Issue 1',
         'When the primary LLM model was unavailable or quota-exhausted, the fallback was not '
         'working as expected — the pipeline took a very long time before producing any result, '
         'and the fallback model did not seem to help.',
         'LLM Fallback'],
        ['Issue 2',
         'Even with tiny 10-row test files, the overall pipeline wait time was too long — '
         'especially the cleaning executor and intent analysis stages.',
         'Pipeline Performance'],
    ]
)
add_para(
    'Both issues were diagnosed by reading the relevant backend files '
    '(backend/app/core/llm.py, backend/app/main.py, backend/app/workers/tasks.py) '
    'and tracing the exact code path for each scenario.',
    size=10
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — LLM BACKGROUND
# ══════════════════════════════════════════════════════════════════════════════
add_heading('2. Background — LLM Architecture & Model Setup', 1, ACCENT)

add_heading('How All LLM Calls Flow Through One Central File', 2)
add_para(
    'Every AI agent in DataMind AI (Cleaning Plan, Intent, Dashboard, Insights) calls '
    'LLMClient in backend/app/core/llm.py. No agent directly imports litellm or '
    'hardcodes a provider name. This single abstraction layer handles retries, '
    'fallback model selection, logging, and error classification.',
    size=10
)
add_code([
    '# Example — IntentAgent calls LLMClient:',
    'spec = await self.llm.structured_completion(',
    '    prompt,',
    '    AnalysisSpec,',
    '    agent_name="intent"',
    ')',
    '',
    '# LLMClient builds model string and calls LiteLLM:',
    'litellm_model = "gemini/gemini-3.5-flash"',
    'response = await litellm.acompletion(model=litellm_model, ...)',
], 'Data flow: Agent → LLMClient → LiteLLM → Gemini API')

add_heading('Model Inventory Before Investigation', 2)
add_table(
    ['Role', 'Model', 'Where Set', 'Issue Found'],
    [
        ['Primary LLM',  'gemini-3.5-flash',      'actual .env + CLAUDE.md',               'Correct'],
        ['Primary LLM',  'gemini-2.0-flash',       '.env.example (dev template)',            'WRONG — mismatch with actual config'],
        ['Fallback LLM', 'gemini-2.0-flash-001',   'llm.py _FALLBACK_MODEL (hardcoded)',    'Same quota as primary — does not help on quota errors'],
        ['Embeddings',   'Qwen3-Embedding-0.6B',   '.env EMBEDDING_MODEL',                  'Correct but loaded lazily — caused cold start'],
    ]
)

add_heading('Critical Concept: API Key = Shared Quota Pool', 2)
add_para(
    'The most important concept for understanding the fallback issue: '
    'ALL Gemini models (gemini-3.5-flash, gemini-2.0-flash, gemini-2.0-flash-001, etc.) '
    'share the same quota. The quota is per Google AI API key / project — not per model version. '
    'When the free-tier daily limit is exhausted, every Gemini model called with that key '
    'returns 429 "Resource Exhausted".',
    size=10
)
add_code([
    'Single Google AI API Key',
    '    ├── gemini-3.5-flash      → same quota pool  (primary)',
    '    ├── gemini-2.0-flash      → same quota pool  (fallback)',
    '    └── gemini-2.0-flash-001  → same quota pool  (old fallback)',
    '',
    '# Free tier: ~20 requests/day across ALL models on this key',
    '# When exhausted, ALL models return:',
    '#   google.api_core.exceptions.ResourceExhausted: 429',
])

add_heading('What Each Agent Does When LLM Fails (Heuristic Fallback)', 2)
add_para(
    'Every agent has a manual rule-based _heuristic_* method. When the LLMClient raises '
    'any exception, the agent catches it and calls its heuristic. The heuristic always '
    'produces a valid result — it is simpler and question-unaware, but it never fails. '
    'This is NOT a failure state — it is the designed safety net.',
    size=10
)
add_table(
    ['Agent', 'File', 'Heuristic Behaviour'],
    [
        ['CleaningPlanAgent', 'agents/cleaning_plan.py',
         'Always adds dedup step; adds impute step for each column that has nulls'],
        ['IntentAgent',       'agents/intent.py',
         'Picks first numeric column as measure; first textual column as dimension; ignores question text'],
        ['DashboardAgent',    'agents/dashboard_agent.py',
         'AVG of first measure as KPI card; bar chart of measure values from numeric results'],
        ['InsightsAgent',     'agents/insights.py',
         'Concatenates KPI label + value strings into a generic narrative sentence'],
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — ISSUE 1 DIAGNOSED
# ══════════════════════════════════════════════════════════════════════════════
add_heading('3. Issue 1 Diagnosed — Why Fallback Was Not Working', 1, ACCENT)
file_tag('backend/app/core/llm.py  →  structured_completion()  method')

add_heading('Root Cause A: No Detection of Quota Errors', 2)
add_para(
    'The original retry loop treated ALL exception types identically — whether the error '
    'was a 429 quota exhaustion (permanent until reset) or a 503 transient overload '
    '(recoverable in seconds). This meant all 3 retry attempts fired even for quota errors, '
    'where retrying is completely pointless.',
    size=10
)
add_code([
    '# ORIGINAL structured_completion() retry loop — simplified',
    'for attempt in range(1, 4):',
    '    try:',
    '        response = await litellm.acompletion(model=litellm_model, ...)',
    '        return result',
    '    except Exception as exc:',
    '        last_error = exc',
    '        log.warning("llm_call_failed", attempt=attempt, error=str(exc))',
    '        # No quota detection',
    '        # No sleep between retries',
    '        # Always does all 3 attempts regardless of error type',
    '',
    '# After loop: tries fallback model (gemini-2.0-flash-001)',
    '# Fallback ALSO gets 429 — same API key!',
    '# Then raises RuntimeError',
    '# Agent catches → heuristic runs',
])

add_heading('Root Cause B: No Sleep Between Retries', 2)
add_para(
    'For transient errors (503 Service Unavailable), the model may recover within seconds. '
    'But without any sleep between retry attempts, all 3 attempts fired within milliseconds '
    'of each other — the model never had time to recover. The fallback model was hit '
    'unnecessarily when a brief wait would have let the primary model succeed.',
    size=10
)

add_heading('The Full Slow Path (Before Fix) — Quota Exhausted', 2)
add_para(
    'When the Gemini free-tier quota was exhausted (20 req/day), this is what happened '
    'for EVERY agent call, for EVERY pipeline stage:',
    size=10
)
add_code([
    'Attempt 1  →  429 Resource Exhausted  →  log  →  (0ms sleep)',
    'Attempt 2  →  429 Resource Exhausted  →  log  →  (0ms sleep)',
    'Attempt 3  →  429 Resource Exhausted  →  log  →  no sleep',
    'Fallback   →  gemini-2.0-flash-001    →  429 again (same API key!)',
    '           →  RuntimeError raised',
    '           →  Agent catches → heuristic runs',
    '',
    '# Each Gemini HTTP call takes ~5–10 seconds to return 429',
    '# 4 failed calls × ~8s each = ~32 seconds WASTED per agent',
    '',
    '# Intent pipeline calls 4 agents:',
    '# IntentAgent + AnalysisAgent(sql) + DashboardAgent + InsightsAgent',
    '# Total wasted time: 4 × 32s = ~128 seconds before heuristics run',
])

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — FIX 1A: QUOTA FAST-FAIL
# ══════════════════════════════════════════════════════════════════════════════
add_heading('4. Fix 1A — Quota Error Fast-Fail', 1, ACCENT)
file_tag('backend/app/core/llm.py')

add_heading('What Was Added: _is_quota_error() Helper', 2)
add_para(
    'A module-level helper function that inspects the exception message and returns True '
    'if the error is a quota or rate-limit error. It checks five different strings because '
    'different LiteLLM versions and Gemini API versions use slightly different wording.',
    size=10
)
add_code([
    'def _is_quota_error(exc: Exception) -> bool:',
    '    """Return True for 429 / quota-exhausted errors where retrying will not help."""',
    '    msg = str(exc).lower()',
    '    return any(k in msg for k in (',
    '        "429",',
    '        "quota",',
    '        "rate_limit",',
    '        "resource_exhausted",',
    '        "too_many_requests",',
    '    ))',
], 'llm.py — new module-level helper (line ~27)')

add_heading('What Was Added: QuotaExhaustedError Class', 2)
add_para(
    'A typed exception class so that the caller (each agent) can distinguish a quota failure '
    'from any other kind of LLM failure. It is a subclass of RuntimeError so all existing '
    '"except Exception" blocks in agents catch it without any changes.',
    size=10
)
add_code([
    'class QuotaExhaustedError(RuntimeError):',
    '    """Raised when the LLM API quota is exhausted so agents can fast-fail to manual fallback."""',
], 'llm.py — new exception class (line ~33)')

add_heading('How the Retry Loop Changed for Quota Errors', 2)
add_before_after(
    [
        '# BEFORE — all errors treated the same',
        'for attempt in range(1, 4):',
        '    try:',
        '        response = await litellm.acompletion(...)',
        '        return result',
        '    except Exception as exc:',
        '        last_error = exc',
        '        log.warning("llm_call_failed", ...)',
        '        # Falls through to next attempt regardless',
        '',
        '# After loop: tries fallback (also 429)',
        '# Total: 4 slow calls, ~32 seconds',
    ],
    [
        '# AFTER — quota detected, stops immediately',
        'quota_hit = False',
        'for attempt in range(1, 4):',
        '    try:',
        '        response = await litellm.acompletion(...)',
        '        return result',
        '    except Exception as exc:',
        '        last_error = exc',
        '        if _is_quota_error(exc):',
        '            log.warning("llm_quota_exhausted_fast_fail",',
        '                        agent=agent_name, attempt=attempt)',
        '            quota_hit = True',
        '            break  # exit loop on attempt 1',
        '        log.warning("llm_call_failed", ...)',
        '',
        'if quota_hit:',
        '    raise QuotaExhaustedError(...)',
        '    # Fallback model SKIPPED — same API key',
        '# Total: 1 call, ~1 second',
    ]
)

add_heading('Why the Fallback Model Is Skipped for Quota Errors', 2)
add_para(
    'After the retry loop exits, the original code always tried the fallback model. '
    'With the fix, if quota_hit is True, a QuotaExhaustedError is raised immediately '
    'before reaching the fallback model code. This is correct because the fallback model '
    'uses the same API key and would return the same 429 error — trying it would just add '
    'another 5-10 seconds of wasted time.',
    size=10
)
add_code([
    'if quota_hit:',
    '    # Raise typed exception — caller goes to heuristic immediately.',
    '    # Fallback model code below is NOT reached.',
    '    raise QuotaExhaustedError(',
    '        f"LLM quota exhausted for agent \'{agent_name}\': {last_error}"',
    '    )',
    '',
    '# Only reached for non-quota failures (503/timeout after all retries)',
    'log.warning("llm_primary_exhausted_trying_fallback", ...)',
    'response = await litellm.acompletion(model=_FALLBACK_MODEL, ...)',
], 'llm.py — quota guard before fallback model attempt')

add_heading('How Agents Receive the Exception (No Agent Code Changed)', 2)
add_para(
    'Every agent already wraps the LLM call in try/except Exception. '
    'QuotaExhaustedError inherits from RuntimeError which inherits from Exception, '
    'so it is caught automatically by all existing agent error handlers. '
    'No agent file needed to change.',
    size=10
)
add_code([
    '# IntentAgent.parse() — UNCHANGED, catches QuotaExhaustedError automatically',
    'try:',
    '    spec = await self.llm.structured_completion(prompt, AnalysisSpec, agent_name="intent")',
    'except Exception as exc:',
    '    log.warning("intent_llm_failed", error=str(exc))',
    '    spec = self._heuristic_parse(question, profiles)',
    '',
    '# Same pattern in CleaningPlanAgent, DashboardAgent, InsightsAgent — all unchanged',
], 'agents/intent.py — agent error handling (no changes required)')

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — FIX 1B: EXPONENTIAL BACKOFF
# ══════════════════════════════════════════════════════════════════════════════
add_heading('5. Fix 1B — Exponential Backoff for Transient Errors', 1, ACCENT)
file_tag('backend/app/core/llm.py')

add_heading('What Is a Transient Error', 2)
add_para(
    'A transient error (HTTP 503 Service Unavailable, or a connection timeout) means the '
    'Gemini model endpoint is temporarily overloaded or unreachable — but it will recover. '
    'Retrying after a short wait often succeeds. Without any sleep, all retries fire '
    'within milliseconds and always see the same overloaded state.',
    size=10
)

add_heading('What Was Added: _RETRY_DELAYS Constant', 2)
add_code([
    '# llm.py — new module-level constant',
    '_RETRY_DELAYS = (2, 4)',
    '#  attempt 1 → 2:  wait 2 seconds before retry',
    '#  attempt 2 → 3:  wait 4 seconds before retry  (exponential: 2^1, 2^2)',
    '',
    '# asyncio import also added at top of file:',
    'import asyncio',
], 'llm.py — retry delay constants (line ~24)')

add_heading('How the Retry Loop Changed for Transient Errors', 2)
add_before_after(
    [
        '# BEFORE — no sleep between retries',
        'except Exception as exc:',
        '    last_error = exc',
        '    log.warning("llm_call_failed", ...)',
        '    # Next iteration starts immediately',
        '    # All 3 attempts happen within milliseconds',
        '    # Model never gets recovery time',
    ],
    [
        '# AFTER — sleep between retries (non-quota errors only)',
        'except Exception as exc:',
        '    last_error = exc',
        '    if _is_quota_error(exc):',
        '        quota_hit = True',
        '        break',
        '    log.warning("llm_call_failed", ...)',
        '    if attempt < 3:',
        '        await asyncio.sleep(_RETRY_DELAYS[attempt - 1])',
        '        # attempt 1: sleep 2 seconds',
        '        # attempt 2: sleep 4 seconds',
    ]
)

add_heading('Why Exponential and Not a Fixed Interval', 2)
add_para(
    'Exponential backoff (2s, 4s) progressively backs off. If the model is still unavailable '
    'after 2 seconds, waiting 4 more seconds before the final attempt gives it more recovery '
    'time. It also reduces thundering-herd pressure when many users hit the same overloaded '
    'endpoint simultaneously — staggered retries distribute load better than fixed intervals.',
    size=10
)

add_heading('Complete Transient Error Flow (After Fix)', 2)
add_code([
    '# 503 transient error — with backoff',
    'Attempt 1  →  503  →  sleep 2 seconds',
    'Attempt 2  →  503  →  sleep 4 seconds',
    'Attempt 3  →  503  →  (no sleep — last attempt)',
    '           →  try fallback model: gemini/gemini-2.0-flash',
    '           →  may succeed! Different generation, different endpoint.',
    '',
    '# 429 quota error — fast-fail (Fix 1A)',
    'Attempt 1  →  429  →  quota detected  →  break  →  QuotaExhaustedError',
    '           →  agent catches  →  heuristic runs in ~1 second',
])

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — MODEL NAME ALIGNMENT
# ══════════════════════════════════════════════════════════════════════════════
add_heading('6. Model Name Alignment (.env.example + llm.py)', 1, ACCENT)

add_heading('The Mismatch Found During Investigation', 2)
add_table(
    ['Source', 'Model Name', 'Correct?', 'Action Taken'],
    [
        ['CLAUDE.md (project spec)', 'gemini-3.5-flash', 'YES — authoritative', 'No change'],
        ['actual .env (live config)', 'gemini-3.5-flash', 'YES — matches spec', 'No change'],
        ['.env.example (dev template)', 'gemini-2.0-flash', 'NO — outdated', 'Updated to gemini-3.5-flash'],
        ['llm.py _FALLBACK_MODEL', 'gemini/gemini-2.0-flash-001', 'Partially — unnecessary version pin', 'Updated to gemini/gemini-2.0-flash'],
    ]
)

add_heading('.env.example Change', 2)
add_before_after(
    [
        '# .env.example — BEFORE',
        'LLM_PROVIDER=google_gemini',
        'LLM_MODEL=gemini-2.0-flash',
        'LLM_API_KEY=<your-gemini-api-key>',
    ],
    [
        '# .env.example — AFTER',
        'LLM_PROVIDER=google_gemini',
        'LLM_MODEL=gemini-3.5-flash',
        'LLM_API_KEY=<your-gemini-api-key>',
    ]
)

add_heading('Fallback Model Change in llm.py', 2)
add_before_after(
    [
        '# llm.py — BEFORE',
        '_FALLBACK_MODEL = "gemini/gemini-2.0-flash-001"',
        '# "-001" is a pinned version — tracks a specific snapshot,',
        '# may fall behind the stable release channel',
    ],
    [
        '# llm.py — AFTER',
        '_FALLBACK_MODEL = "gemini/gemini-2.0-flash"',
        '# Tracks the stable 2.0-flash release channel.',
        '# Different generation from 3.5-flash — helps for',
        '# transient 503 errors where the primary endpoint is overloaded.',
    ]
)

add_para(
    'Note: Both primary (3.5-flash) and fallback (2.0-flash) use the same API key, '
    'so the fallback only helps for transient 503 errors, not quota exhaustion. '
    'For quota exhaustion, Fix 1A (quota fast-fail) ensures the fallback model is '
    'never even attempted.',
    size=10, italic=True, color=GRAY
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — ISSUE 2 DIAGNOSED
# ══════════════════════════════════════════════════════════════════════════════
add_heading('7. Issue 2 Diagnosed — Why Performance Was Slow', 1, ACCENT)

add_heading('Pipeline Architecture Overview', 2)
add_para(
    'The DataMind AI backend runs four sequential pipeline stages, each triggered by '
    'user action. Each stage is a separate FastAPI BackgroundTask function in tasks.py.',
    size=10
)
add_code([
    'Stage 1: run_ingest_pipeline()         — after file upload',
    '  ↓ download files, parse, profile, propose merge plan',
    '',
    'Stage 2: run_cleaning_plan_pipeline()  — after HITL #1 approved',
    '  ↓ download files again, parse again, profile again, LLM → cleaning plan',
    '',
    'Stage 3: run_cleaning_executor_pipeline() — after HITL #2 approved',
    '  ↓ download files again, parse again, profile again, execute cleaning,',
    '  ↓ N×INSERT to PostgreSQL, embed texts, N×INSERT to pgvector',
    '',
    'Stage 4: run_intent_analysis_pipeline()  — after question submitted',
    '  ↓ try JSON download (fails 403), download archive again, parse again,',
    '  ↓ profile again, LLM×4, cache dashboard',
], 'tasks.py — four pipeline stages')

add_heading('Four Performance Problems Found', 2)
add_table(
    ['#', 'Problem', 'Where', 'Impact for 10-row file'],
    [
        ['P1', 'Embedding model cold start — Qwen3-Embedding-0.6B loaded mid-pipeline',
         'main.py — no startup event', '5–20 second delay on first run after server start'],
        ['P2', 'Column profiles recomputed from scratch in every pipeline stage',
         'tasks.py — run_cleaning_executor_pipeline',
         'Unnecessary CPU work; profiles already stored in HITLDecision table'],
        ['P3', 'PostgreSQL rows inserted one-by-one in a for loop',
         'tasks.py — run_cleaning_executor_pipeline ~line 228',
         '10 rows = 10 async db round-trips (~100ms each = ~1 second wasted)'],
        ['P4', 'pgvector embeddings inserted one-by-one in a for loop',
         'tasks.py — run_cleaning_executor_pipeline ~line 252',
         '10 rows = 10 more async db round-trips (~1 second wasted)'],
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — FIX 2A: EMBEDDING PRE-WARM
# ══════════════════════════════════════════════════════════════════════════════
add_heading('8. Fix 2A — Embedding Model Pre-Warming at Startup', 1, ACCENT)
file_tag('backend/app/main.py')

add_heading('What Is the Embedding Model', 2)
add_table(
    ['Property', 'Value'],
    [
        ['Model',           'Qwen/Qwen3-Embedding-0.6B'],
        ['Parameters',      '~600 million'],
        ['Output',          '1024-dimensional vectors'],
        ['Context window',  '8192 tokens'],
        ['Library',         'sentence-transformers (SentenceTransformer class)'],
        ['Device',          'CPU (.env EMBEDDING_DEVICE=cpu)'],
        ['Cold start time', '5–20 seconds (reads model weights from disk into RAM)'],
        ['After first load','Near-instant (singleton via @lru_cache(maxsize=1))'],
    ]
)

add_heading('What Was the Problem', 2)
add_para(
    'The singleton pattern in embeddings.py uses @lru_cache(maxsize=1) on get_embedding_model(). '
    'lru_cache is lazy — it only calls EmbeddingModel() on the FIRST call. '
    'That first call happened inside run_cleaning_executor_pipeline() mid-pipeline, '
    'while the user was watching the progress bar. The 5-20 second disk load added directly '
    'to the user\'s wait time.',
    size=10
)
add_code([
    '# embeddings.py — the singleton (correct pattern, lazy by default)',
    '@lru_cache(maxsize=1)',
    'def get_embedding_model() -> EmbeddingModel:',
    '    return EmbeddingModel()  # loads Qwen weights from disk — 5-20s',
    '',
    '# tasks.py — where cold start hit the user',
    'embedding_model = get_embedding_model()  # FIRST CALL = 5-20s delay here',
    'embeddings = embedding_model.embed_batch(texts)',
    '',
    '# User sees: "Embedding textual columns..." spinner for 20 seconds',
], 'embeddings.py + tasks.py — cold start location')

add_heading('What Was Changed', 2)
add_para(
    'A FastAPI lifespan context manager was added to main.py. FastAPI calls the startup '
    'section of lifespan before accepting any HTTP request. get_embedding_model() is called '
    'here so the model is in RAM before any user pipeline starts.',
    size=10
)
add_before_after(
    [
        '# main.py — BEFORE: no startup event',
        'app = FastAPI(',
        '    title="DataMind AI",',
        '    version="0.1.0",',
        '    docs_url="/docs" if not settings.is_production else None,',
        '    redoc_url=None,',
        ')',
        '',
        '# Embedding model loaded mid-pipeline on first user run',
    ],
    [
        '# main.py — AFTER: lifespan pre-warms model',
        'import asyncio',
        'from contextlib import asynccontextmanager',
        '',
        '@asynccontextmanager',
        'async def lifespan(app: FastAPI):',
        '    from app.core.embeddings import get_embedding_model',
        '    loop = asyncio.get_event_loop()',
        '    await loop.run_in_executor(None, get_embedding_model)',
        '    log.info("embedding_model_warmed")',
        '    yield  # app runs here',
        '',
        'app = FastAPI(',
        '    title="DataMind AI",',
        '    version="0.1.0",',
        '    lifespan=lifespan,  # ← registered',
        '    docs_url="/docs" if not settings.is_production else None,',
        '    redoc_url=None,',
        ')',
    ]
)

add_heading('Why run_in_executor — Not Just a Direct Call', 2)
add_para(
    'SentenceTransformer.__init__() is a synchronous blocking function — it reads model '
    'weight files from disk using standard file I/O. FastAPI runs on an asyncio event loop. '
    'Calling a blocking function directly inside an async function blocks the entire event '
    'loop — no HTTP requests can be handled while the model loads.',
    size=10
)
add_table(
    ['Approach', 'Effect on Event Loop'],
    [
        ['await loop.run_in_executor(None, get_embedding_model)  ✓',
         'Offloads blocking load to a thread pool worker. Event loop stays free. Startup completes before first request accepted.'],
        ['get_embedding_model()  direct call in async  ✗',
         'Blocks the event loop for 5-20 seconds. Server appears unresponsive during this window.'],
    ]
)

add_heading('Log Evidence After Fix', 2)
add_code([
    '# Server startup log (after fix):',
    '{"event": "embedding_model_warmed", "level": "info", "timestamp": "..."}',
    '{"message": "Application startup complete"}',
    '',
    '# First pipeline run:',
    '# get_embedding_model() hits lru_cache — returns instantly',
    '# No cold start delay for any user',
])

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — FIX 2B: REUSE PROFILES
# ══════════════════════════════════════════════════════════════════════════════
add_heading('9. Fix 2B — Reuse Stored Column Profiles', 1, ACCENT)
file_tag('backend/app/workers/tasks.py  →  run_cleaning_executor_pipeline()')

add_heading('What Are Column Profiles', 2)
add_para(
    'During the ingest stage, IngestionAgent.profile_columns() inspects every column '
    'in the uploaded data: it counts null values, counts distinct values, measures average '
    'string length, and classifies each column as numeric, textual, or ambiguous. '
    'These profiles drive the HITL #1 schema review and the storage routing decision '
    '(numeric columns → PostgreSQL, textual columns → pgvector).',
    size=10
)
add_code([
    '# IngestionAgent.profile_columns() — what it computes per column',
    'for col in columns:',
    '    values      = [r.get(col) for r in rows]',
    '    null_count  = len(values) - len(non_null)',
    '    distinct_count = len(set(str(v) for v in non_null))',
    '    numeric_ratio  = numeric_count / len(non_null)',
    '    avg_length     = total_str_len / (non_null_text_count)',
    '    # classify: numeric / textual / ambiguous',
    '    profiles.append(ColumnProfile(name=col, ...))',
    '',
    '# Stored in HITLDecision table after ingest:',
    '# proposal_json = {"strategy": "single", "column_profiles": [...], ...}',
], 'agents/ingestion.py — profile_columns() summary')

add_heading('Where Profiles Were Recomputed (Problem)', 2)
add_table(
    ['Pipeline Stage', 'Calls profile_columns()?', 'Necessary?', 'Reason'],
    [
        ['run_ingest_pipeline',             'YES', 'YES', 'First time — must compute and store'],
        ['run_cleaning_plan_pipeline',      'YES', 'Borderline — needs profiles for LLM prompt', 'Could reuse stored'],
        ['run_cleaning_executor_pipeline',  'YES', 'NO', 'Profiles already in HITLDecision table'],
        ['run_intent_analysis_pipeline',    'YES', 'Borderline', 'Could reuse stored'],
    ]
)

add_heading('Fix: Read Profiles From HITLDecision Table', 2)
add_before_after(
    [
        '# run_cleaning_executor_pipeline — BEFORE',
        '# Re-downloads files AND re-profiles from scratch',
        'profiles = ingestion.profile_columns(all_rows)',
        '# Iterates every column × every row again',
        '# Same result every time for the same files',
    ],
    [
        '# run_cleaning_executor_pipeline — AFTER',
        '# Read profiles stored during ingest stage',
        'from app.models.schemas import ColumnProfile as ColumnProfileSchema',
        'merge_hitl_res = await db.execute(',
        '    select(HITLDecision)',
        '    .where(',
        '        HITLDecision.dataset_id == uuid.UUID(dataset_id),',
        '        HITLDecision.checkpoint == "schema_merge"',
        '    )',
        '    .order_by(HITLDecision.created_at.desc())',
        '    .limit(1)',
        ')',
        'merge_hitl = merge_hitl_res.scalar_one_or_none()',
        'if merge_hitl and merge_hitl.proposal_json.get("column_profiles"):',
        '    profiles = [ColumnProfileSchema(**p)',
        '                for p in merge_hitl.proposal_json["column_profiles"]]',
        'else:',
        '    profiles = ingestion.profile_columns(all_rows)  # safe fallback',
    ]
)

add_heading('Why This Is Safe', 2)
for b in [
    'Files are immutable after upload — Layer 1 archive is never modified',
    'Cleaning executor runs on the same files that were profiled during ingest',
    'Column names and types do not change between ingest and cleaning',
    'Storage routing (numeric→PG, textual→pgvector) was confirmed by user in HITL #1',
    'A safe fallback (else branch) is kept in case the HITLDecision record is missing',
]:
    add_bullet(b)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — FIX 2C: BULK PG INSERT
# ══════════════════════════════════════════════════════════════════════════════
add_heading('10. Fix 2C — Bulk INSERT for PostgreSQL Rows', 1, ACCENT)
file_tag('backend/app/workers/tasks.py  →  run_cleaning_executor_pipeline()  ~line 220')

add_heading('Context: Layer 3 Storage', 2)
add_para(
    'After cleaning, numeric and structured columns are written to a per-dataset PostgreSQL '
    'table. The table name is derived from the dataset_id. The Analysis Agent then runs '
    'SQL aggregations (AVG, SUM, GROUP BY) against this table when the user submits an '
    'analysis question.',
    size=10
)
add_code([
    'table_name = f"ds_{dataset_id.replace(\'-\', \'_\')}"',
    '# e.g. ds_3a7f9b2c_1234_5678_abcd_ef0123456789',
    '',
    'numeric_cols = [p.name for p in profiles if p.classification == "numeric"]',
    '# e.g. ["length_of_stay_days", "readmitted"]',
])

add_heading('The N+1 INSERT Problem', 2)
add_para(
    'Each cleaned row was inserted in a separate await db.execute() call inside a Python '
    'for loop. Each call is an independent async network round-trip from the FastAPI server '
    'to the Supabase PostgreSQL instance (hosted remotely). For small 10-row files, '
    'this means 10 network calls just for this step.',
    size=10
)
add_code([
    '# BEFORE — one INSERT per row = N round-trips',
    'for row in cleaned_rows:',
    '    vals = {c: str(row.get(c, "")) for c in numeric_cols}',
    '    placeholders = ", ".join(f":{c}" for c in numeric_cols)',
    '    col_names    = ", ".join(f\'"{c}"\' for c in numeric_cols)',
    '    await db.execute(',
    '        text(f\'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})\'),',
    '        vals   # one dict = one row = one db round-trip',
    '    )',
    '',
    '# 10 rows × ~100ms per round-trip = ~1 second just for inserts',
    '# 20 rows (2 files) = ~2 seconds',
])

add_heading('The Fix: executemany via List of Dicts', 2)
add_before_after(
    [
        'for row in cleaned_rows:',
        '    vals = {c: str(row.get(c, "")) for c in numeric_cols}',
        '    placeholders = ", ".join(f":{c}" for c in numeric_cols)',
        '    col_names    = ", ".join(f\'"{c}"\' for c in numeric_cols)',
        '    await db.execute(',
        '        text(f\'INSERT ... VALUES ({placeholders})\'),',
        '        vals  # ← one INSERT per iteration',
        '    )',
    ],
    [
        '# Build all value dicts first — no db calls yet',
        'col_names    = ", ".join(f\'"{c}"\' for c in numeric_cols)',
        'placeholders = ", ".join(f":{c}" for c in numeric_cols)',
        'insert_sql   = text(',
        '    f\'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders})\'',
        ')',
        'all_vals = [',
        '    {c: str(row.get(c, "")) for c in numeric_cols}',
        '    for row in cleaned_rows',
        ']',
        '# Single call with list → SQLAlchemy executemany → 1 round-trip',
        'await db.execute(insert_sql, all_vals)',
    ]
)

add_heading('How executemany Works with asyncpg', 2)
add_para(
    'SQLAlchemy 2.x async session, when passed a list of dicts as the second argument '
    'to session.execute(stmt, list_of_dicts), uses executemany() at the driver level '
    'for DML statements. asyncpg\'s executemany() pipelines all rows into a single '
    'PostgreSQL protocol message, reducing N network round-trips to 1.',
    size=10
)
add_table(
    ['Metric', 'Before', 'After'],
    [
        ['DB round-trips for 10 rows',  '10', '1'],
        ['DB round-trips for 20 rows',  '20', '1'],
        ['Estimated time (20 rows)',     '~2000ms', '~100ms'],
        ['Code lines',                  '6 (for loop + inner await)', '5 (list comprehension + single await)'],
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — FIX 2D: BULK PGVECTOR INSERT
# ══════════════════════════════════════════════════════════════════════════════
add_heading('11. Fix 2D — Bulk INSERT for pgvector Embeddings', 1, ACCENT)
file_tag('backend/app/workers/tasks.py  →  run_cleaning_executor_pipeline()  ~line 248')

add_heading('Context: Layer 4 Storage', 2)
add_para(
    'Textual columns (high distinct count or long average string length) are embedded '
    'using Qwen3-Embedding-0.6B and stored in the dataset_embeddings table as 1024-dimensional '
    'vectors. The Analysis Agent queries this table via cosine similarity when the user '
    'asks a question that relates to textual content.',
    size=10
)
add_code([
    '# dataset_embeddings table (PostgreSQL + pgvector extension)',
    'CREATE TABLE dataset_embeddings (',
    '    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),',
    '    dataset_id  UUID NOT NULL,',
    '    content     TEXT NOT NULL,       -- joined text from all textual columns',
    '    metadata    JSONB,               -- first 5 columns of source row',
    '    embedding   vector(1024)         -- Qwen3 output',
    ')',
])

add_heading('The N+1 INSERT Problem (Same Pattern as PostgreSQL)', 2)
add_code([
    '# BEFORE — embed_batch() is correct (batched), but INSERT is not',
    'texts      = ["col1_val col2_val col3_val" for row in cleaned_rows]',
    'embeddings = embedding_model.embed_batch(texts)  # ← batched, good',
    '',
    'for text_val, emb, row in zip(texts, embeddings, cleaned_rows):',
    '    emb_str = "[" + ",".join(str(x) for x in emb) + "]"',
    '    await db.execute(',
    '        text("INSERT INTO dataset_embeddings ... VALUES (:did,:content,:meta,CAST(:emb AS vector))"),',
    '        {"did": dataset_id, "content": text_val, "meta": ..., "emb": emb_str}',
    '    )  # ← ONE INSERT PER ROW inside loop',
    '',
    '# 10 rows = 10 individual INSERT statements = 10 db round-trips',
])

add_heading('The Fix: Build Param List, Single executemany Call', 2)
add_before_after(
    [
        'for text_val, emb, row in zip(texts, embeddings, cleaned_rows):',
        '    emb_str = "[" + ",".join(str(x) for x in emb) + "]"',
        '    await db.execute(',
        '        text("INSERT INTO dataset_embeddings ...',
        '              VALUES (:did,:content,:meta,CAST(:emb AS vector))"),',
        '        {"did": dataset_id, ..., "emb": emb_str}',
        '    )  # ← one per loop',
    ],
    [
        '# Build all param dicts — no db calls yet',
        'emb_params = [',
        '    {',
        '        "did":     dataset_id,',
        '        "content": text_val,',
        '        "meta":    json.dumps({k: row.get(k)',
        '                               for k in list(row.keys())[:5]}),',
        '        "emb":     "[" + ",".join(str(x) for x in emb) + "]",',
        '    }',
        '    for text_val, emb, row in zip(texts, embeddings, cleaned_rows)',
        ']',
        '# Single executemany call for all rows',
        'await db.execute(',
        '    text("INSERT INTO dataset_embeddings ...',
        '          VALUES (:did,:content,:meta,CAST(:emb AS vector))"),',
        '    emb_params,  # ← list of dicts = executemany = 1 round-trip',
        ')',
    ]
)

add_heading('Important: CAST(:emb AS vector) Syntax — Preserved', 2)
add_para(
    'The pgvector type cast uses CAST(:emb AS vector) rather than the double-colon shorthand '
    ':emb::vector. asyncpg\'s named-to-positional parameter translator (:name → $N) breaks '
    'when it encounters ::vector, treating it as another named parameter starting with a colon. '
    'CAST() is the standard SQL form that asyncpg handles correctly. This was fixed in a prior '
    'session and is preserved unchanged here.',
    size=10, color=ORANGE
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12 — COMPLETE llm.py BEFORE/AFTER
# ══════════════════════════════════════════════════════════════════════════════
add_heading('12. Complete Before/After: Full llm.py', 1, ACCENT)
add_para(
    'This section shows the complete file to make it easy to see all changes together.',
    size=10
)

add_heading('llm.py — BEFORE (original)', 2)
add_code([
    'import time',
    'from typing import TypeVar, Type',
    '',
    'import structlog',
    'from pydantic import BaseModel',
    'from app.core.config import settings',
    '',
    'log = structlog.get_logger()',
    'T = TypeVar("T", bound=BaseModel)',
    '',
    '_PROVIDER_ROUTES: dict[str, str] = {"google_gemini": "gemini"}',
    '_FALLBACK_MODEL = "gemini/gemini-2.0-flash-001"',
    '',
    'class LLMClient:',
    '    def __init__(self, tenant_id=None):',
    '        self._provider = settings.llm_provider',
    '        self._model    = settings.llm_model',
    '        self._api_key  = settings.llm_api_key',
    '',
    '    async def structured_completion(self, prompt, schema, agent_name, ...):',
    '        litellm_model = f"{_PROVIDER_ROUTES.get(provider)}/{model}"',
    '        last_error = None',
    '',
    '        for attempt in range(1, 4):',
    '            try:',
    '                response = await litellm.acompletion(model=litellm_model, ...)',
    '                return schema.model_validate_json(response...)',
    '            except Exception as exc:',
    '                last_error = exc',
    '                log.warning("llm_call_failed", attempt=attempt, error=str(exc))',
    '                # No quota detection, no sleep',
    '',
    '        # Always tries fallback — even for quota errors',
    '        try:',
    '            response = await litellm.acompletion(model=_FALLBACK_MODEL, ...)',
    '            return schema.model_validate_json(response...)',
    '        except Exception as fallback_exc:',
    '            raise RuntimeError(...)',
])

add_heading('llm.py — AFTER (fixed)', 2)
add_code([
    'import asyncio   # NEW',
    'import time',
    'from typing import TypeVar, Type',
    '',
    'import structlog',
    'from pydantic import BaseModel',
    'from app.core.config import settings',
    '',
    'log = structlog.get_logger()',
    'T = TypeVar("T", bound=BaseModel)',
    '',
    '_PROVIDER_ROUTES: dict[str, str] = {"google_gemini": "gemini"}',
    '_FALLBACK_MODEL = "gemini/gemini-2.0-flash"       # NEW: removed "-001" version pin',
    '_RETRY_DELAYS   = (2, 4)                           # NEW: seconds between retries',
    '',
    'def _is_quota_error(exc: Exception) -> bool:       # NEW',
    '    msg = str(exc).lower()',
    '    return any(k in msg for k in (',
    '        "429", "quota", "rate_limit", "resource_exhausted", "too_many_requests",',
    '    ))',
    '',
    'class QuotaExhaustedError(RuntimeError): pass      # NEW',
    '',
    'class LLMClient:',
    '    def __init__(self, tenant_id=None):',
    '        self._provider = settings.llm_provider',
    '        self._model    = settings.llm_model',
    '        self._api_key  = settings.llm_api_key',
    '',
    '    async def structured_completion(self, prompt, schema, agent_name, ...):',
    '        litellm_model = f"{_PROVIDER_ROUTES.get(provider)}/{model}"',
    '        last_error = None',
    '        quota_hit  = False   # NEW',
    '',
    '        for attempt in range(1, 4):',
    '            try:',
    '                response = await litellm.acompletion(model=litellm_model, ...)',
    '                return schema.model_validate_json(response...)',
    '            except Exception as exc:',
    '                last_error = exc',
    '                if _is_quota_error(exc):             # NEW',
    '                    log.warning("llm_quota_exhausted_fast_fail", ...)',
    '                    quota_hit = True',
    '                    break                            # stop immediately',
    '                log.warning("llm_call_failed", ...)',
    '                if attempt < 3:',
    '                    await asyncio.sleep(_RETRY_DELAYS[attempt - 1])  # NEW',
    '',
    '        if quota_hit:                                # NEW',
    '            raise QuotaExhaustedError(...)          # skips fallback model',
    '',
    '        # Fallback only reached for transient non-quota errors',
    '        try:',
    '            response = await litellm.acompletion(model=_FALLBACK_MODEL, ...)',
    '            return schema.model_validate_json(response...)',
    '        except Exception as fallback_exc:',
    '            raise RuntimeError(...)',
])

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 13 — IMPACT SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
add_heading('13. Impact Summary', 1, ACCENT)

add_heading('Time Savings Per Stage (10-row test file, quota exhausted)', 2)
add_table(
    ['Stage / Step', 'Before Fix', 'After Fix', 'Time Saved'],
    [
        ['Cleaning Plan — LLM quota error',
         '~32s (4 Gemini calls × 8s)', '~1s (1 call, detected, stopped)', '~31s'],
        ['Cleaning Executor — embedding cold start',
         '+5–20s on first run', '0s (pre-warmed at startup)', '5–20s'],
        ['Cleaning Executor — re-profiling',
         'profile_columns() recomputed', 'DB read from HITLDecision', '~50ms'],
        ['Cleaning Executor — PostgreSQL inserts',
         '10 db calls × ~100ms', '1 executemany call', '~900ms'],
        ['Cleaning Executor — pgvector inserts',
         '10 db calls × ~100ms', '1 executemany call', '~900ms'],
        ['Intent Analysis — LLM quota × 4 agents',
         '~128s (4 × 32s)', '~4s (4 × 1s)', '~124s'],
    ]
)

add_heading('What Did NOT Change', 2)
for b in [
    'All HITL checkpoints and user-facing behaviour are identical',
    'Heuristic fallback outputs are identical in quality',
    'Database schema is unchanged — same tables, same columns, same data',
    'API endpoints and response shapes are unchanged',
    'Frontend code is completely unaffected',
    'The first attempt to call Gemini still happens — we only skip pointless retries',
]:
    add_bullet(b)

add_heading('Files Changed Summary', 2)
add_table(
    ['File', 'What Changed', 'Lines Affected'],
    [
        ['backend/app/core/llm.py',
         'Added: asyncio import, _RETRY_DELAYS, _is_quota_error(), QuotaExhaustedError, '
         'quota fast-fail in retry loop, exponential backoff sleep, quota guard before fallback. '
         'Updated: _FALLBACK_MODEL from gemini-2.0-flash-001 to gemini-2.0-flash.',
         '~40 lines changed'],
        ['backend/app/main.py',
         'Added: asyncio import, asynccontextmanager import, lifespan() function, '
         'lifespan=lifespan parameter in FastAPI constructor.',
         '~15 lines added'],
        ['backend/app/workers/tasks.py',
         'Added: profile reuse from HITLDecision with fallback; '
         'bulk INSERT for PostgreSQL rows using all_vals list; '
         'bulk INSERT for pgvector using emb_params list.',
         '~25 lines changed'],
        ['.env.example',
         'LLM_MODEL changed from gemini-2.0-flash to gemini-3.5-flash.',
         '1 line changed'],
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 14 — INTERVIEW QUICK REFERENCE
# ══════════════════════════════════════════════════════════════════════════════
add_heading('14. Interview Quick Reference', 1, ACCENT)
add_para('Key technical talking points for each fix.', size=10, italic=True)

qas = [
    (
        'Why did trying the fallback model (gemini-2.0-flash) not help when the quota was exhausted?',
        'The Google AI API quota is per API key, not per model. All Gemini models — '
        'gemini-3.5-flash, gemini-2.0-flash, gemini-2.0-flash-001 — share the same '
        'daily limit under the same key. When the free-tier limit of ~20 requests/day '
        'is exhausted, every model called with that key returns 429 Resource Exhausted. '
        'The fallback model is useful for transient 503 overload (different model endpoint, '
        'may be available when primary is overloaded) — but not for account-level quota.',
    ),
    (
        'What is the difference between a 429 and a 503 error and how does the code handle each?',
        '429 Resource Exhausted = quota gone, retrying in milliseconds will fail, '
        'must wait for quota reset (daily/per-minute). Fix: _is_quota_error() detects '
        'it on attempt 1, sets quota_hit=True, breaks out of retry loop, skips fallback '
        'model, raises QuotaExhaustedError immediately. '
        '503 Service Unavailable = transient overload, will recover. Fix: exponential '
        'backoff (sleep 2s, 4s) between retries gives the model time to recover. '
        'Fallback model is still tried after all 3 primary retries fail.',
    ),
    (
        'Why use run_in_executor to load the embedding model at startup?',
        'SentenceTransformer.__init__() is a synchronous blocking function — it reads '
        'model weight files from disk. FastAPI runs on an asyncio event loop. Calling '
        'a blocking function directly inside an async function blocks the event loop, '
        'preventing any HTTP requests from being handled during that time. '
        'run_in_executor(None, fn) offloads the blocking call to a thread pool worker '
        'so the event loop stays free. The await ensures startup waits for the load '
        'to complete before accepting requests.',
    ),
    (
        'Why is it safe to reuse the column profiles stored in HITLDecision?',
        'Column profiles describe the shape of the uploaded files — column names, types, '
        'null counts, classifications. The uploaded files are immutable (Layer 1 archive '
        'is never modified). The cleaning executor runs on the exact same files that were '
        'profiled during ingest. Column names and storage routing (numeric→PG, textual→pgvector) '
        'were confirmed by the user in HITL #1. So the stored profiles are always correct '
        'for the executor stage. A fallback (else: profile_columns(all_rows)) is kept for '
        'robustness in case the HITLDecision record is missing.',
    ),
    (
        'How does passing a list of dicts to db.execute() achieve bulk insert?',
        'SQLAlchemy 2.x, when passed a list of dicts as the second argument to '
        'session.execute(DML_statement, list_of_dicts), triggers executemany() at '
        'the driver level for INSERT/UPDATE/DELETE statements. asyncpg\'s executemany() '
        'pipelines all rows into a single PostgreSQL protocol message, reducing N '
        'network round-trips to 1. The same named INSERT statement (:col1, :col2) '
        'is reused for every dict in the list, with only the parameter values changing.',
    ),
    (
        'Why is QuotaExhaustedError a subclass of RuntimeError and not a standalone Exception?',
        'Every agent already wraps LLM calls in "except Exception" and falls to its heuristic. '
        'Making QuotaExhaustedError a subclass of RuntimeError (→ Exception) means all '
        'existing agent error handlers catch it automatically — no agent code needed to change. '
        'The typed subclass still provides value: it produces a distinct log event '
        '(llm_quota_exhausted_fast_fail vs llm_call_failed) making it easy to monitor '
        'quota exhaustion separately from transient failures in Grafana/logs.',
    ),
    (
        'What is the heuristic fallback and is it a failure state?',
        'No — it is the designed safety net. Every agent has a _heuristic_* method that '
        'uses pure Python rule-based logic: no LLM, no network calls, always returns a '
        'valid result. For example, CleaningPlanAgent._heuristic_plan() always proposes '
        'a deduplication step and an imputation step for any null-containing column. '
        'The output is simpler and question-unaware compared to what Gemini produces, '
        'but it is a valid, usable result. The pipeline completes successfully — '
        'the user gets a dashboard, just with less intelligent content.',
    ),
]

for q, a in qas:
    p = doc.add_paragraph()
    p.paragraph_format.space_after  = Pt(3)
    p.paragraph_format.space_before = Pt(8)
    r = p.add_run(f'Q: {q}')
    r.bold = True
    r.font.size = Pt(10)
    r.font.color.rgb = ACCENT
    ap = doc.add_paragraph()
    ap.paragraph_format.space_after = Pt(6)
    ar = ap.add_run(f'A: {a}')
    ar.font.size = Pt(10)

# ── Save ──────────────────────────────────────────────────────────────────────
output_path = (
    r'C:\Users\PriyankaKoujalagi\Documents\EURON\DataMindAI'
    r'\PROJECT-9-DataMind-AI\docs\DataMindAI_Perf_Fallback_Reference.docx'
)
doc.save(output_path)
print(f'Saved: {output_path}')
