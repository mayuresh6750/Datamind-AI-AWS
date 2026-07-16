"""Generate DataMind AI HITL Reference Word Document."""
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy

doc = Document()

# ── Page margins ──────────────────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin   = Cm(2.5)
    section.right_margin  = Cm(2.5)

# ── Style helpers ─────────────────────────────────────────────────────────────
ACCENT   = RGBColor(0x1E, 0x40, 0xAF)   # blue-800
GREEN    = RGBColor(0x16, 0x65, 0x34)
RED      = RGBColor(0x99, 0x17, 0x17)
GRAY     = RGBColor(0x37, 0x41, 0x51)
CODEBG   = RGBColor(0xF1, 0xF5, 0xF9)
DARKBG   = RGBColor(0x1E, 0x29, 0x3B)

def set_cell_bg(cell, hex_color: str):
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement('w:shd')
    shd.set(qn('w:val'),   'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'),  hex_color)
    tcPr.append(shd)

def set_row_bg(row, hex_color: str):
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

def add_code_block(lines: list[str], label: str = ''):
    if label:
        lp = doc.add_paragraph()
        lp.paragraph_format.space_after  = Pt(2)
        lp.paragraph_format.space_before = Pt(6)
        lr = lp.add_run(label)
        lr.bold = True
        lr.font.size  = Pt(9)
        lr.font.color.rgb = GRAY

    tbl = doc.add_table(rows=1, cols=1)
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

def add_before_after(before_lines, after_lines, before_label='BEFORE (buggy)', after_label='AFTER (fixed)'):
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
    tbl = doc.add_table(rows=1+len(rows), cols=len(headers))
    tbl.style = 'Table Grid'
    hdr_row = tbl.rows[0]
    set_row_bg(hdr_row, header_bg)
    for i, h in enumerate(headers):
        c = hdr_row.cells[i]
        c.paragraphs[0].clear()
        r = c.paragraphs[0].add_run(h)
        r.bold = True
        r.font.size = Pt(9)
        r.font.color.rgb = RGBColor.from_string(header_fg)
    for ri, row_data in enumerate(rows):
        row = tbl.rows[ri+1]
        if ri % 2 == 1:
            set_row_bg(row, alt_bg)
        for ci, val in enumerate(row_data):
            c = row.cells[ci]
            c.paragraphs[0].clear()
            r = c.paragraphs[0].add_run(str(val))
            r.font.size = Pt(9)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)
    return tbl

def add_bullet(text, level=0):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_after = Pt(3)
    run = p.add_run(text)
    run.font.size = Pt(10)
    return p

def add_hr():
    p = doc.add_paragraph()
    p.paragraph_format.space_after  = Pt(2)
    p.paragraph_format.space_before = Pt(2)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'),   'single')
    bottom.set(qn('w:sz'),    '6')
    bottom.set(qn('w:space'), '1')
    bottom.set(qn('w:color'), 'CBD5E1')
    pBdr.append(bottom)
    pPr.append(pBdr)

def file_tag(path: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_after  = Pt(4)
    p.paragraph_format.space_before = Pt(8)
    r1 = p.add_run('📄 File: ')
    r1.bold = True
    r1.font.size = Pt(10)
    r1.font.color.rgb = ACCENT
    r2 = p.add_run(path)
    r2.font.name = 'Courier New'
    r2.font.size  = Pt(9)
    r2.font.color.rgb = ACCENT
    return p

# ══════════════════════════════════════════════════════════════════════════════
# COVER PAGE
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
rs = sub.add_run('HITL Pipeline — Frontend & Backend\nTechnical & Functional Reference Guide')
rs.bold = True
rs.font.size = Pt(16)
rs.font.color.rgb = GRAY

doc.add_paragraph().paragraph_format.space_after = Pt(20)

meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
meta.add_run('Branch: Priyanka-K/feat-backend   |   Sessions: 2026-06-16 & 2026-06-17').font.size = Pt(10)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — PROJECT OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════
add_heading('1. Project Overview', 1, ACCENT)
add_para(
    'DataMind AI is an agentic data intelligence platform that transforms raw business data '
    '(CSV, XLSX, JSON, Parquet) into clean, contextual dashboards and actionable insights — '
    'without requiring SQL or Python knowledge. It is built around four core principles.',
    size=10, space_after=8
)
add_table(
    ['Principle', 'Description'],
    [
        ['Domain-first', 'Users select their domain (Finance, Healthcare, Retail, Marketing, Operations, Other) so all downstream agents use domain-appropriate vocabulary and KPIs.'],
        ['User-controlled modeling', 'Users decide how multiple files are merged: UNION (stack rows), JOIN (shared key), or kept separate.'],
        ['Human-In-The-Loop (HITL)', 'No cleaning or analysis runs without explicit user approval at defined checkpoints. Every step is proposed, reviewed, and then executed.'],
        ['Type-aware storage routing', 'Numeric/structured columns → PostgreSQL; free-text columns → pgvector (Supabase Vector) for semantic search.'],
    ]
)

add_heading('Technology Stack', 2)
add_table(
    ['Layer', 'Technology', 'Responsibility'],
    [
        ['Frontend',       'Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn/ui', 'User UI, Admin UI, HITL review screens'],
        ['Backend',        'Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy (async)',        'REST API, request validation, async pipeline dispatch'],
        ['Database',       'Supabase (PostgreSQL + pgvector)',                               'Structured data, vector embeddings, metadata'],
        ['Auth',           'Supabase Auth (JWT)',                                            'Sign-up, login, session management, RBAC'],
        ['Storage',        'Supabase Storage',                                               'Raw file archive, presigned upload URLs'],
        ['LLM',            'Google Gemini 3.5 Flash (via LiteLLM abstraction)',              'Cleaning plan generation, insights narrative'],
        ['Embeddings',     'Qwen3-Embedding-0.6B',                                          'Free-text column embeddings for pgvector'],
        ['Agent Framework','FastAPI BackgroundTasks + tasks.py (Phase 1)',                                  'Multi-agent pipeline, retry, HITL gates'],
        ['Package manager','pnpm (frontend) / uv (backend)',                                  'Dependency management'],
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — HITL ARCHITECTURE
# ══════════════════════════════════════════════════════════════════════════════
add_heading('2. HITL Architecture & Pipeline Flow', 1, ACCENT)
add_para(
    'HITL (Human-In-The-Loop) checkpoints are mandatory pauses in the automated pipeline where '
    'the user must review and approve agent outputs before execution continues. '
    'No data transformation or analysis runs silently.',
    size=10, space_after=8
)

add_heading('Pipeline Stages', 2)
add_code_block([
    'User uploads file(s)',
    '    ↓',
    'Ingestion Agent: detect format → parse rows → profile columns → propose merge plan',
    '    ↓',
    '[HITL #1]  User reviews schema, merge strategy, column types → Confirms',
    '    ↓',
    'Cleaning Plan Agent: generates numbered list of proposed cleaning actions with confidence scores',
    '    ↓',
    '[HITL #2]  User approves / rejects individual steps → Submits',
    '    ↓',
    'Cleaning Executor Agent: runs ONLY approved steps → writes cleaned data to storage',
    '    ↓',
    '[HITL #3]  User submits natural-language analysis question → AI restates for confirmation',
    '    ↓',
    'Analysis Agent → Dashboard Agent → Insights Agent',
    '    ↓',
    'Dashboard rendered in browser',
], 'Pipeline (linear view)')

add_heading('Dataset Status State Machine', 2)
add_para(
    'The datasets table has a status column tracking pipeline progress. '
    'Each HITL checkpoint is a gate — the pipeline cannot advance until the user acts.',
    size=10
)
add_code_block([
    'uploaded',
    '  → profiling              (Ingestion Agent running)',
    '  → awaiting_hitl_merge   (HITL #1 gate — user must review schema)',
    '  → cleaning_plan         (Cleaning Plan Agent running)',
    '  → awaiting_hitl_cleaning (HITL #2 gate — user must review cleaning steps)',
    '  → executing             (Cleaning Executor running approved steps)',
    '  → ready                 (pipeline complete)',
], 'status field values')

add_heading('Critical Distinction: job.status vs job.current_step', 2)
add_para(
    'These are two separate fields in the job registry response. New team members frequently confuse them.',
    size=10
)
add_table(
    ['Field', 'Example values', 'Meaning'],
    [
        ['job.status',       '"queued", "running", "complete", "error"', 'Is the background worker thread alive?'],
        ['job.current_step', '"awaiting_hitl_merge", "awaiting_hitl_cleaning"', 'Which pipeline stage is the dataset at?'],
    ]
)
add_para(
    'The frontend must check job.current_step (not job.status) to know when to redirect '
    'to a HITL review page. This was the root cause of Bug #1 (Upload page never redirected).',
    size=10, italic=True
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — BUG FIX 1: COLUMN CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════════
add_heading('3. Bug Fix #1 — Column Classification (Backend)', 1, ACCENT)
file_tag('backend/app/agents/ingestion.py  →  profile_columns()  method, lines ~120–131')

add_heading('Functional Description', 2)
add_para(
    'The Ingestion Agent inspects each column in an uploaded dataset and classifies it as one of '
    'three types: numeric (suitable for SQL aggregation), textual (suitable for vector/semantic search), '
    'or ambiguous (user decides). These classifications are shown in HITL #1 and drive how data is '
    'routed to storage — numeric columns go to PostgreSQL, textual columns go to pgvector.',
    size=10
)

add_heading('Classification Rules (from CLAUDE.md)', 2)
add_table(
    ['Class', 'Detection Rule', 'Storage Destination'],
    [
        ['numeric/structured', '≥90% of values parse as float  OR  low-cardinality categorical (≤50 distinct values, short text)', 'PostgreSQL'],
        ['textual/semantic',   'Average string length > 40 chars  OR  distinct count > 50% of total rows', 'pgvector (Supabase Vector)'],
        ['ambiguous',          'Neither rule matches — user must decide in HITL #1', 'User chooses in HITL #1'],
    ]
)

add_heading('What Was Wrong', 2)
add_para(
    'The conditions were evaluated in the wrong order. The low-cardinality check '
    '(distinct_count ≤ 50) ran BEFORE the textual check. In small test files (10–20 rows), '
    'virtually every column — including free-text columns like patient_name, diagnosis, and notes — '
    'trivially has ≤50 distinct values. So they all matched the categorical/numeric branch '
    'before the textual branch was ever evaluated.',
    size=10
)
add_para(
    'Symptom: Every column showed "numeric" classification on the validate page, '
    'even obviously textual columns like "notes" and "patient_name".',
    size=10, italic=True, color=RED
)

add_heading('Before / After Code Change', 2)
add_before_after(
    [
        '# WRONG ORDER — low-cardinality check runs before textual',
        'if numeric_ratio >= 0.9:',
        '    classification = "numeric"',
        '    dtype = "float"',
        'elif distinct_count <= MAX_CARDINALITY_FOR_STRUCTURED:  # ← fires for all text cols',
        '    classification = "numeric"                          #   in small files!',
        '    dtype = "categorical"',
        'elif avg_length >= MIN_AVG_LENGTH_FOR_TEXTUAL \\',
        '        or distinct_count > 0.5 * len(rows):           # ← never reached',
        '    classification = "textual"',
        '    dtype = "text"',
        'else:',
        '    classification = "ambiguous"',
        '    dtype = "text"',
    ],
    [
        '# CORRECT ORDER — textual check before low-cardinality check',
        'if numeric_ratio >= 0.9:',
        '    classification = "numeric"',
        '    dtype = "float"',
        'elif avg_length >= MIN_AVG_LENGTH_FOR_TEXTUAL \\',
        '        or distinct_count > 0.5 * len(rows):  # ← check textual FIRST',
        '    classification = "textual"',
        '    dtype = "text"',
        'elif distinct_count <= MAX_CARDINALITY_FOR_STRUCTURED:',
        '    classification = "numeric"                # only for truly short,',
        '    dtype = "categorical"                     # low-cardinality columns',
        'else:',
        '    classification = "ambiguous"',
        '    dtype = "text"',
    ]
)

add_heading('Constants Used', 2)
add_code_block([
    'MAX_CARDINALITY_FOR_STRUCTURED = 50   # ≤50 distinct values → numeric/categorical',
    'MIN_AVG_LENGTH_FOR_TEXTUAL     = 40   # avg string length ≥40 chars → textual',
], 'ingestion.py — module-level constants')

add_heading('Verification', 2)
add_para(
    'After the fix, uploading the healthcare test CSV showed the correct classifications:',
    size=10
)
add_table(
    ['Column', 'Before Fix', 'After Fix', 'Correct?'],
    [
        ['patient_id',           'numeric', 'textual',  '✓ (high distinct ratio: 10/10 rows)'],
        ['patient_name',         'numeric', 'textual',  '✓ (free-text name)'],
        ['diagnosis',            'numeric', 'textual',  '✓ (free-text diagnosis)'],
        ['length_of_stay_days',  'numeric', 'numeric',  '✓ (integer values)'],
        ['readmitted',           'numeric', 'numeric',  '✓ (binary categorical: Yes/No)'],
        ['notes',                'numeric', 'textual',  '✓ (long free-text)'],
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — BUG FIX 2: UNION PROFILE MERGING
# ══════════════════════════════════════════════════════════════════════════════
add_heading('4. Bug Fix #2 — Union Multi-File Profile Merging (Backend)', 1, ACCENT)

add_heading('Files Changed', 2)
add_table(
    ['File', 'Function / Method'],
    [
        ['backend/app/agents/ingestion.py',  'propose_merge_plan() — added all_rows optional parameter'],
        ['backend/app/workers/tasks.py',     'run_ingest_pipeline() — passes all_rows to propose_merge_plan'],
    ]
)

add_heading('Functional Description', 2)
add_para(
    'When a user uploads two or more files with identical column schemas, the Ingestion Agent '
    'recommends a UNION merge strategy (stack all rows from all files). The schema table on the '
    'validate page should show column statistics (null counts, distinct counts, average lengths) '
    'computed across the combined dataset — not just one file.',
    size=10
)

add_heading('What Was Wrong', 2)
add_para(
    'The propose_merge_plan() function was returning column profiles taken only from the first file. '
    'The remaining files\' rows were ignored entirely for stats computation.',
    size=10
)
add_para(
    'Symptom: Uploading two 10-row healthcare CSVs showed distinct_count = 10 for patient_id '
    'instead of the correct value of 20 (10 + 10 combined).',
    size=10, italic=True, color=RED
)

add_heading('Before / After — ingestion.py', 2)
add_before_after(
    [
        'def propose_merge_plan(self, file_profiles):',
        '    ...',
        '    if all(s == all_col_sets[0] for s in all_col_sets):',
        '        all_profiles = file_profiles[0][1]  # ← ONLY first file stats!',
        '        return MergePlan(',
        '            strategy="union",',
        '            confidence=0.92,',
        '            column_profiles=all_profiles,',
        '        )',
    ],
    [
        'def propose_merge_plan(',
        '    self,',
        '    file_profiles: list[tuple[str, list[ColumnProfile]]],',
        '    all_rows: list[dict] | None = None,  # ← new optional param',
        ') -> MergePlan:',
        '    ...',
        '    if all(s == all_col_sets[0] for s in all_col_sets):',
        '        # Recompute over ALL combined rows for accurate stats',
        '        all_profiles = (',
        '            self.profile_columns(all_rows)',
        '            if all_rows is not None',
        '            else file_profiles[0][1]',
        '        )',
        '        return MergePlan(',
        '            strategy="union",',
        '            confidence=0.92,',
        '            column_profiles=all_profiles,',
        '        )',
    ]
)

add_heading('Before / After — tasks.py', 2)
add_before_after(
    [
        '# all_rows accumulated but NOT passed into merge plan',
        'all_rows: list[dict] = []',
        'for filename, path in zip(...):',
        '    rows = ingestion.parse_content(fmt, content)',
        '    file_profiles.append((filename, profiles))',
        '    all_rows.extend(rows)',
        '',
        'merge_plan = ingestion.propose_merge_plan(file_profiles)  # ← missing all_rows',
    ],
    [
        '# all_rows now passed into propose_merge_plan',
        'all_rows: list[dict] = []',
        'for filename, path in zip(...):',
        '    rows = ingestion.parse_content(fmt, content)',
        '    file_profiles.append((filename, profiles))',
        '    all_rows.extend(rows)',
        '',
        'merge_plan = ingestion.propose_merge_plan(file_profiles, all_rows)  # ✓ fixed',
    ]
)

add_para(
    'Note: The all_rows parameter is optional (default None) to preserve backward compatibility '
    'with supervisor.py which only handles single-file datasets and never needs multi-file merging.',
    size=10, italic=True
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — BUG FIX 3: UPLOAD PAGE REDIRECT
# ══════════════════════════════════════════════════════════════════════════════
add_heading('5. Bug Fix #3 — Upload Page Never Redirected (Frontend)', 1, ACCENT)
file_tag('frontend/app/(user)/page.tsx')

add_heading('Functional Description', 2)
add_para(
    'After a file is uploaded and the Ingestion Agent finishes profiling, the upload page should '
    'automatically redirect to the HITL #1 validate page. The page polls the job status every 2 '
    'seconds to detect when the pipeline reaches the awaiting_hitl_merge stage.',
    size=10
)

add_heading('What Was Wrong', 2)
add_para(
    'The polling logic checked job.status === "awaiting_hitl_merge" to trigger the redirect. '
    'However, job.status only ever holds worker lifecycle values: queued, running, complete, or error. '
    'The pipeline stage lives in a completely separate field: job.current_step.',
    size=10
)
add_para(
    'Since job.status never equals "awaiting_hitl_merge", the redirect condition never fired. '
    'The user was stuck on the upload page forever, even though the pipeline had finished.',
    size=10, italic=True, color=RED
)

add_heading('Before / After Code Change', 2)
add_before_after(
    [
        '// Checking the WRONG field',
        'const TERMINAL_STATUSES = [',
        '  "awaiting_hitl_merge",  // ← NEVER in job.status',
        '  "complete",',
        '  "error"',
        ']',
        '',
        'if (TERMINAL_STATUSES.includes(job.status)) {',
        '  clearInterval(pollerRef.current)',
        '  // redirect logic ...',
        '}',
    ],
    [
        '// Checking the CORRECT fields',
        'const TERMINAL_STEPS = ["awaiting_hitl_merge"]',
        '',
        'const jobFailed = job.status === "error"',
        'const stepIsTerminal =',
        '  job.current_step !== null &&',
        '  TERMINAL_STEPS.includes(job.current_step)',
        '',
        'if (jobFailed || stepIsTerminal || attempts > 90) {',
        '  clearInterval(pollerRef.current)',
        '  pollerRef.current = null',
        '  setUploading(false)',
        '',
        '  if (job.current_step === "awaiting_hitl_merge") {',
        '    window.location.href = `/validate/${dataset_id}`  // ✓ redirect',
        '  } else if (jobFailed) {',
        '    setError(job.error ?? "Pipeline failed.")',
        '  }',
        '}',
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — TYPE SYSTEM FIXES
# ══════════════════════════════════════════════════════════════════════════════
add_heading('6. Frontend Type System Fixes', 1, ACCENT)
add_para(
    'TypeScript type definitions must exactly match the backend Pydantic schemas. '
    'Mismatches cause runtime crashes (TypeError, undefined property access) even though TypeScript '
    'compiles without errors — because the actual data comes from the API at runtime, not from the type file.',
    size=10
)

add_heading('6.1  frontend/types/pipeline.ts — HITL #1 Types', 2)
file_tag('frontend/types/pipeline.ts')
add_before_after(
    [
        '// Wrong — assumed files[] nesting',
        'interface ColumnSchema { name: string; type: string }',
        'interface FileSchema {',
        '  filename: string',
        '  columns: ColumnSchema[]  // ← doesn\'t exist in backend',
        '}',
        'interface MergePlan {',
        '  files: FileSchema[]  // ← backend sends flat list, not this',
        '  rationale: string    // ← backend never sends this field',
        '  cartesian_risk: bool // ← backend never sends this field',
        '}',
        '',
        '// Caused crash: "Cannot read properties of undefined',
        '//  (reading \'length\')" on plan.files.length',
    ],
    [
        '// Correct — matches backend/app/models/schemas.py exactly',
        'export type ColumnClassification =',
        '  "numeric" | "textual" | "ambiguous"',
        '',
        'export interface ColumnProfile {',
        '  name: string',
        '  dtype: string',
        '  null_count: number',
        '  distinct_count: number',
        '  avg_length: number | null   // null for numeric columns',
        '  classification: ColumnClassification',
        '}',
        '',
        'export interface MergePlan {',
        '  strategy: "single"|"union"|"join"|"separate"',
        '  join_key: string | null',
        '  confidence: number',
        '  column_profiles: ColumnProfile[]  // flat list',
        '}',
    ]
)

add_heading('6.2  frontend/types/pipeline.ts — HITL #2 Types', 2)
add_before_after(
    [
        '// Wrong — used "actions", "id", "title" — none exist in backend',
        'interface CleaningAction {',
        '  id: string       // ← backend uses step_id: int',
        '  type: string     // ← backend uses action: str',
        '  title: string    // ← backend has no title field',
        '  ...impute_options  // ← not in backend schema',
        '}',
        'interface CleaningPlan {',
        '  dataset_id: string    // ← not in backend response',
        '  actions: CleaningAction[]  // ← backend uses steps[]',
        '  generated_at: string  // ← not in backend response',
        '}',
    ],
    [
        '// Correct — matches backend/app/models/schemas.py exactly',
        'export interface CleaningStep {',
        '  step_id: number    // integer (not string)',
        '  action: "deduplicate"|"impute"|"coerce_type"|"flag_outlier"',
        '  column: string | null  // null for row-level ops (dedup)',
        '  method: string         // human-readable method description',
        '  rationale: string',
        '  confidence: number',
        '  rows_affected: number',
        '  before_sample: Record<string, any> | null',
        '  after_sample: Record<string, any> | null',
        '}',
        'export interface CleaningPlan {',
        '  steps: CleaningStep[]   // "steps", not "actions"',
        '  total_rows_before: number',
        '  total_rows_after: number',
        '}',
    ]
)

add_heading('6.3  frontend/types/api.ts — CleaningPlanDecision', 2)
file_tag('frontend/types/api.ts')
add_before_after(
    [
        '// Wrong — per-step status approach backend does not accept',
        'interface CleaningDecision {',
        '  step_id: string   // ← should be number',
        '  status: "approved" | "modified" | "rejected"',
        '  override: string | null',
        '}',
        '// And payload was wrapped: { decisions: [...] }',
        '// Backend rejected this with 422 Unprocessable Entity',
    ],
    [
        '// Correct — matches backend CleaningPlanDecision schema',
        'export interface CleaningPlanDecision {',
        '  approved_step_ids: number[]  // list of int step_ids approved',
        '  step_modifications: Record<number, Record<string, any>>',
        '}',
        '// Payload sent directly (no wrapper):',
        '// { approved_step_ids: [1,2,3], step_modifications: {} }',
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — HITL #1 FRONTEND
# ══════════════════════════════════════════════════════════════════════════════
add_heading('7. HITL Checkpoint #1 — Schema & Merge Validation (Frontend)', 1, ACCENT)

add_heading('7.1  Validate Page', 2)
file_tag('frontend/app/(user)/validate/[id]/page.tsx')
add_para(
    'This is the main HITL #1 review page. It fetches the merge plan from the backend, '
    'renders the schema table and merge proposal, tracks all user overrides in local state, '
    'and submits the full decision payload on confirm or reject.',
    size=10
)

add_heading('State Variables', 2)
add_table(
    ['State Variable', 'Type', 'Purpose'],
    [
        ['plan',             'MergePlan | null',          'Merge plan fetched from GET /datasets/{id}/merge-plan'],
        ['typeOverrides',    'Record<string, string>',    'Per-column classification overrides (column → "numeric"/"textual"/"ambiguous")'],
        ['excludedColumns',  'string[]',                  'Columns unchecked by the user (will be excluded from dataset)'],
        ['strategy',         'string | null',             'Effective merge strategy — defaults to plan.strategy, user can change'],
        ['joinKey',          'string | null',             'Effective join key — only used when strategy is "join"'],
        ['saving',           'boolean',                   'True while API call is in progress (prevents double-submit)'],
        ['error',            'string | null',             'Backend error message shown to user if submission fails'],
    ]
)

add_heading('Decision Payload Sent to Backend', 2)
add_code_block([
    'POST /api/v1/datasets/{id}/merge-plan/decision',
    '',
    '{',
    '  "approved": true,                       // or false for "Reject & start over"',
    '  "merge_strategy_override": "join",      // only sent if user changed from recommendation',
    '  "join_key_override": "patient_id",      // only relevant when strategy is "join"',
    '  "excluded_columns": ["notes"],           // columns user unchecked',
    '  "type_routing_overrides": {             // classification changes by user',
    '    "patient_id": "numeric"',
    '  }',
    '}',
], 'Approve path example')

add_heading('Approve vs Reject paths', 2)
add_table(
    ['Button', 'approved value', 'Backend effect', 'Frontend redirect'],
    [
        ['Confirm & proceed to cleaning', 'true',  'Triggers cleaning plan agent, dataset.status → "cleaning_plan"', 'router.push("/clean/{id}")'],
        ['Reject & start over',           'false', 'Resets dataset.status → "uploaded", no job started',            'router.push("/")  (upload page)'],
    ]
)

add_heading('7.2  SchemaTable Component', 2)
file_tag('frontend/components/user/SchemaTable.tsx')
add_para(
    'Displays a table of all column profiles with per-column interactive controls. '
    'Every column row has an include/exclude checkbox, type label, statistics, and a classification dropdown.',
    size=10
)

add_heading('Props', 2)
add_table(
    ['Prop', 'Type', 'Purpose'],
    [
        ['columns',                'ColumnProfile[]',                   'Array of column profiles from backend'],
        ['excludedColumns',        'string[]',                          'Controlled list of excluded column names (from parent state)'],
        ['onClassificationChange', '(col, classification) => void',     'Called when user changes classification dropdown for a column'],
        ['onExcludeToggle',        '(col, excluded: boolean) => void',  'Called when user checks/unchecks the include checkbox'],
    ]
)

add_heading('Table Columns Displayed', 2)
add_table(
    ['Column', 'Content', 'Behaviour'],
    [
        ['(checkbox)',      'Include/exclude toggle',          'Unchecked → row dims to 50% opacity; classification dropdown disables'],
        ['Column',         'Column name (monospace)',          '—'],
        ['Type',           'dtype from backend',               'Values: float, text, categorical, etc.'],
        ['Nulls',          'null_count',                       '—'],
        ['Distinct',       'distinct_count',                   '—'],
        ['Avg length',     'avg_length rounded to 2 decimals', 'Shows "—" for numeric columns (avg_length is null)'],
        ['Classification', 'Dropdown: numeric/textual/ambiguous', 'Blue/purple/orange colour coding; disabled when row is excluded'],
    ]
)

add_heading('avg_length rounding fix', 2)
add_before_after(
    [
        '// Showed raw float: 33.55555555555556',
        '<td>{c.avg_length ?? "—"}</td>',
    ],
    [
        '// Rounded to 2 decimal places',
        '<td>',
        '  {c.avg_length !== null',
        '    ? c.avg_length.toFixed(2)',
        '    : "—"}',
        '</td>',
    ]
)

add_heading('7.3  MergeProposal Component', 2)
file_tag('frontend/components/user/MergeProposal.tsx')
add_para(
    'Shows the agent\'s recommended merge strategy with a confidence badge, and lets the user '
    'override both the strategy and the join key via dropdowns.',
    size=10
)

add_heading('Confidence Badge Colours', 2)
add_table(
    ['Score Range', 'Badge Colour', 'Interpretation'],
    [
        ['≥ 0.90',      'Green',  'High confidence — agent is very sure'],
        ['0.70 – 0.89', 'Yellow', 'Medium confidence — review recommended'],
        ['0.50 – 0.69', 'Orange', 'Low confidence — consider overriding'],
        ['< 0.50',      'Red',    'Very low confidence — manual review required'],
    ]
)

add_heading('Strategy Override Behaviour', 2)
for b in [
    'Strategy dropdown shows all 4 options: single, union, join, separate',
    'Defaults to the agent\'s recommendation (plan.strategy)',
    'When user overrides, a "(recommended: X)" hint appears next to the dropdown',
    'If user switches to JOIN, a merge-key dropdown appears populated with all column names',
    'If user switches AWAY from JOIN, the join key resets to null automatically',
    'merge_strategy_override is only included in the decision payload when the user changed it',
]:
    add_bullet(b)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — HITL #2 FRONTEND
# ══════════════════════════════════════════════════════════════════════════════
add_heading('8. HITL Checkpoint #2 — Cleaning Plan Review (Frontend)', 1, ACCENT)

add_heading('8.1  Cleaning Plan Page', 2)
file_tag('frontend/app/(user)/clean/[id]/page.tsx')
add_para(
    'HITL #2 review page. Fetches the cleaning plan (with polling until ready), '
    'renders numbered steps with confidence indicators, pre-checks high-confidence steps, '
    'and submits the user\'s approve/reject decisions.',
    size=10
)

add_heading('State Variables', 2)
add_table(
    ['State Variable', 'Type', 'Purpose'],
    [
        ['plan',         'CleaningPlan | null',  'Cleaning plan fetched from backend'],
        ['approvedIds',  'Set<number>',           'Set of step_id values user has approved'],
        ['pollAttempts', 'number',                'Counter of how many times polling has retried'],
        ['saving',       'boolean',               'Prevents double-submit'],
        ['error',        'string | null',         'Backend error on submission failure'],
    ]
)

add_heading('Pre-checking Logic (Confidence Framework)', 2)
add_code_block([
    'function initialApproved(steps: CleaningStep[]): Set<number> {',
    '  // Pre-check all steps with confidence >= 0.70 per HITL framework',
    '  return new Set(',
    '    steps',
    '      .filter((s) => s.confidence >= 0.7)',
    '      .map((s) => s.step_id)',
    '  )',
    '}',
], 'Called once when plan loads — sets initial checkbox state')

add_heading('Per-Step UI Elements', 2)
add_table(
    ['UI Element', 'Content', 'Behaviour'],
    [
        ['Step number',       'Circular badge with index (1, 2, 3…)',    '—'],
        ['Action label',      'Human-readable action (e.g. "Fix data type")', 'Mapped via ACTION_LABEL dict from backend action codes'],
        ['Column pill',       'Affected column in monospace code style',  'Only shown when step.column is not null'],
        ['Confidence badge',  '95% confidence (colour-coded)',           'Green/yellow/orange/red per score range'],
        ['Rationale',         'Paragraph from backend',                  '—'],
        ['Method + Rows',     'Method description and rows_affected',    'Shown on same line'],
        ['Warning text',      'Red text for very low confidence',        'Only shown when confidence < 0.50'],
        ['Approve checkbox',  'Checked/unchecked',                       'Toggles step in/out of approvedIds set; unchecked rows dim'],
    ]
)

add_heading('Decision Payload Sent to Backend', 2)
add_code_block([
    'POST /api/v1/datasets/{id}/cleaning-plan/decision',
    '',
    '{',
    '  "approved_step_ids": [1, 2, 3, 4],  // step_ids the user approved',
    '  "step_modifications": {}              // reserved for future per-step overrides',
    '}',
], 'Example: all 4 steps approved')

add_heading('8.2  Polling Mechanism', 2)
add_para(
    'The cleaning plan page redirects from HITL #1 immediately after the decision is posted. '
    'However, the cleaning plan agent runs asynchronously — it takes several seconds. '
    'During this time, GET /cleaning-plan returns HTTP 409 ("Cleaning plan not ready yet"). '
    'Without polling, the page shows "Loading cleaning plan…" forever.',
    size=10
)

add_heading('Why polling was needed', 2)
add_code_block([
    '// BEFORE — single fetch, silently swallows 409',
    'useEffect(() => {',
    '  getCleaningPlan(id)',
    '    .then((r) => setPlan(r.data))',
    '    .catch(() => {})   // ← 409 silently ignored; user stuck forever',
    '}, [id])',
], 'Before')
add_code_block([
    '// AFTER — interval-based polling with cleanup',
    'const pollerRef = useRef<ReturnType<typeof setInterval> | null>(null)',
    '',
    'useEffect(() => {',
    '  const tryFetch = () => {',
    '    getCleaningPlan(id)',
    '      .then((r) => {',
    '        if (pollerRef.current) {',
    '          clearInterval(pollerRef.current)  // stop once plan is ready',
    '          pollerRef.current = null',
    '        }',
    '        setPlan(r.data)',
    '        setApprovedIds(initialApproved(r.data.steps))',
    '      })',
    '      .catch(() => {',
    '        setPollAttempts((n) => n + 1)  // 409 = not ready, keep polling',
    '      })',
    '  }',
    '',
    '  tryFetch()                                       // immediate first attempt',
    '  pollerRef.current = setInterval(tryFetch, 3000) // retry every 3 seconds',
    '',
    '  return () => {                                   // cleanup on page unmount',
    '    if (pollerRef.current) clearInterval(pollerRef.current)',
    '  }',
    '}, [id])',
], 'After')

add_heading('Why useRef (not useState) for the interval ID', 2)
add_table(
    ['Option', 'Why not suitable', ''],
    [
        ['useState',      'Every state update triggers a re-render; storing an interval ID in state would cause unnecessary re-renders on every poll tick', ''],
        ['plain variable','Loses its value between re-renders; interval would "escape" and become impossible to clear', ''],
        ['useRef ✓',     'Persists across re-renders without triggering re-renders; stable reference to the timer ID', ''],
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — SHARED INFRASTRUCTURE
# ══════════════════════════════════════════════════════════════════════════════
add_heading('9. Shared Frontend Infrastructure', 1, ACCENT)

add_heading('9.1  lib/pipelineApi.ts', 2)
file_tag('frontend/lib/pipelineApi.ts')
add_para(
    'Centralises all pipeline-related API calls. Two fixes were applied here.',
    size=10
)

add_heading('Fix 1 — Removed incorrect decisions wrapper', 2)
add_before_after(
    [
        '// Wrong — wrapped payload causes 422 Unprocessable Entity',
        'export const submitCleaningDecisions = (',
        '  datasetId: string,',
        '  decisions: CleaningDecision[]',
        ') => api.post(',
        '  `/datasets/${datasetId}/cleaning-plan/decision`,',
        '  { decisions }  // ← extra wrapper object backend rejects',
        ')',
    ],
    [
        '// Correct — send CleaningPlanDecision directly as body',
        'export const submitCleaningDecisions = (',
        '  datasetId: string,',
        '  body: CleaningPlanDecision',
        ') => api.post(',
        '  `/datasets/${datasetId}/cleaning-plan/decision`,',
        '  body  // ← flat body matches backend Pydantic model',
        ')',
    ]
)

add_heading('Fix 2 — Updated import to match renamed type', 2)
add_before_after(
    [
        "import type { ..., CleaningDecision, ... } from '@/types/api'",
    ],
    [
        "import type { ..., CleaningPlanDecision, ... } from '@/types/api'",
    ]
)

add_heading('9.2  next.config.js — Rewrite Ordering Fix', 2)
file_tag('frontend/next.config.js')
add_para(
    'Next.js API Route Handlers (local files in app/api/...) and backend rewrites '
    '(/api/v1/* → localhost:8000) were conflicting. The issue was rewrite precedence order.',
    size=10
)

add_heading('How Next.js Rewrite Ordering Works', 2)
add_table(
    ['Type', 'When it runs', 'Effect'],
    [
        ['beforeFiles (array default)', 'Before checking local Route Handlers', 'Rewrites override local routes — local API routes get bypassed'],
        ['afterFiles ✓',               'After checking local Route Handlers',   'Local routes take precedence; unmatched requests fall through to rewrite'],
        ['fallback',                    'Only if no route matched at all',       '—'],
    ]
)

add_before_after(
    [
        '// Default array form = beforeFiles semantics',
        '// Local API routes get bypassed by the rewrite',
        'async rewrites() {',
        '  return [',
        '    {',
        '      source: "/api/v1/:path*",',
        '      destination: "http://localhost:8000/api/v1/:path*",',
        '    },',
        '  ]',
        '}',
    ],
    [
        '// afterFiles = local Route Handlers checked first',
        'async rewrites() {',
        '  return {',
        '    afterFiles: [',
        '      {',
        '        source: "/api/v1/:path*",',
        '        destination:',
        '          `${process.env.NEXT_PUBLIC_API_URL',
        '            || "http://localhost:8000"}/api/v1/:path*`,',
        '      },',
        '    ],',
        '  }',
        '}',
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — TEST DATA FILES
# ══════════════════════════════════════════════════════════════════════════════
add_heading('10. Test Data Files', 1, ACCENT)
add_para(
    'Two CSV files were created for end-to-end testing. Both have identical column schemas '
    '(8 columns) enabling UNION merge testing.',
    size=10
)

add_table(
    ['File', 'Rows', 'Patient IDs', 'Date Range', 'Location'],
    [
        ['test_healthcare.csv',   '10', 'P001–P010', 'Feb 2024', 'C:\\Users\\PriyankaKoujalagi\\Documents\\EURON\\DataMindAI\\'],
        ['test_healthcare_2.csv', '10', 'P011–P020', 'Mar 2024', 'C:\\Users\\PriyankaKoujalagi\\Documents\\EURON\\DataMindAI\\'],
    ]
)

add_heading('Columns in Both Files', 2)
add_table(
    ['Column', 'Sample Values', 'Expected Classification'],
    [
        ['patient_id',           'P001, P002, …',                          'textual (100% distinct ratio)'],
        ['patient_name',         'John Carter, Maria Gomez, …',            'textual (avg length > threshold)'],
        ['diagnosis',            'Pneumonia, Type 2 Diabetes, …',          'textual (distinct text values)'],
        ['admission_date',       '2024-02-01, 2024-02-03, …',             'textual (date strings, no date parser yet)'],
        ['discharge_date',       '2024-02-06, 2024-02-05, …',             'textual (same as above)'],
        ['length_of_stay_days',  '5, 2, 11, 8, …',                        'numeric (all values parse as float)'],
        ['readmitted',           'Yes, No',                                 'numeric/categorical (2 distinct values ≤ 50)'],
        ['notes',                'Responded well to antibiotics, …',        'textual (long free-text, avg length ≈ 33–35 chars)'],
    ]
)

add_heading('Test Scenarios', 2)
add_table(
    ['Test Scenario', 'Files to Upload', 'What to Verify'],
    [
        ['Single-file flow',           'test_healthcare.csv only',          'Strategy = single (99% confidence, green badge)'],
        ['UNION merge flow',           'Both files together in one batch',  'Strategy = union (92% confidence); distinct_count for patient_id = 20'],
        ['Column classification',      'Either file',                       'patient_name, diagnosis, notes → textual; length_of_stay_days → numeric'],
        ['Confidence colour rendering', 'Either file',                       'Cleaning plan steps: 95% green, 85% yellow'],
        ['Exclude column',             'Either file',                       'Uncheck "notes" → excluded_columns: ["notes"] in decision payload'],
        ['Strategy override to JOIN',  'Either file',                       'Change dropdown to JOIN → merge-key dropdown appears'],
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — API CONTRACT REFERENCE
# ══════════════════════════════════════════════════════════════════════════════
add_heading('11. API Contract Reference', 1, ACCENT)
add_para(
    'All endpoints require Authorization: Bearer <jwt_token> header. '
    'JWT is issued by Supabase Auth on login and stored in the frontend.',
    size=10
)

add_heading('HITL #1 Endpoints', 2)
add_code_block([
    'GET  /api/v1/datasets/{dataset_id}/merge-plan',
    '',
    'Returns: MergePlan',
    '{',
    '  "strategy": "single",       // single | union | join | separate',
    '  "join_key": null,',
    '  "confidence": 0.99,',
    '  "column_profiles": [',
    '    {',
    '      "name": "patient_id",',
    '      "dtype": "text",',
    '      "null_count": 0,',
    '      "distinct_count": 10,',
    '      "avg_length": 4.0,',
    '      "classification": "textual"',
    '    },',
    '    ...',
    '  ]',
    '}',
    '',
    'Status guard: Returns HTTP 409 if dataset.status != "awaiting_hitl_merge"',
], 'GET merge-plan')

add_code_block([
    'POST /api/v1/datasets/{dataset_id}/merge-plan/decision',
    '',
    'Body: MergePlanDecision',
    '{',
    '  "approved": true,',
    '  "merge_strategy_override": null,        // null = keep agent recommendation',
    '  "join_key_override": null,',
    '  "excluded_columns": [],',
    '  "type_routing_overrides": {}',
    '}',
    '',
    'Returns: { "job_id": "...", "status": "queued" }',
    'Effect:  Triggers run_cleaning_plan_pipeline background task',
    '         dataset.status → "cleaning_plan"',
    '',
    'If approved=false:  dataset.status → "uploaded"  (no job started)',
], 'POST merge-plan/decision')

add_heading('HITL #2 Endpoints', 2)
add_code_block([
    'GET  /api/v1/datasets/{dataset_id}/cleaning-plan',
    '',
    'Returns: CleaningPlan',
    '{',
    '  "steps": [',
    '    {',
    '      "step_id": 1,',
    '      "action": "coerce_type",',
    '      "column": "admission_date",',
    '      "method": "Parse string to datetime format YYYY-MM-DD",',
    '      "rationale": "The admission_date is stored as text...",',
    '      "confidence": 0.95,',
    '      "rows_affected": 20,',
    '      "before_sample": null,',
    '      "after_sample": null',
    '    }',
    '  ],',
    '  "total_rows_before": 20,',
    '  "total_rows_after": 20',
    '}',
    '',
    'Status guard: Returns HTTP 409 if dataset.status != "awaiting_hitl_cleaning"',
    'Frontend behaviour: Polls every 3 seconds until 200 OK received',
], 'GET cleaning-plan')

add_code_block([
    'POST /api/v1/datasets/{dataset_id}/cleaning-plan/decision',
    '',
    'Body: CleaningPlanDecision',
    '{',
    '  "approved_step_ids": [1, 2, 3, 4],',
    '  "step_modifications": {}',
    '}',
    '',
    'Returns: { "job_id": "...", "status": "queued" }',
    'Effect:  Triggers run_cleaning_executor_pipeline background task',
    '         dataset.status → "executing"',
], 'POST cleaning-plan/decision')

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12 — END TO END FLOW
# ══════════════════════════════════════════════════════════════════════════════
add_heading('12. End-to-End Flow Walkthrough (Tested)', 1, ACCENT)
add_para(
    'This section documents the full flow as manually tested using the healthcare CSV test files.',
    size=10
)

steps = [
    ('Step 1 — Domain Selection',
     'User navigates to the app, selects Healthcare domain. Domain Agent loads the healthcare prompt pack for all downstream agents.',
     []),
    ('Step 2 — File Upload',
     'User drags test_healthcare.csv onto the upload zone. The frontend requests a presigned URL from POST /upload-url, uploads directly to Supabase Storage, then calls POST /ingest to kick off the pipeline.',
     ['GET /jobs/{job_id} polled every 2 seconds', 'Upload page shows "Pipeline: running"',
      'When job.current_step === "awaiting_hitl_merge", page auto-redirects to /validate/{id}']),
    ('Step 3 — HITL #1 Validate Page',
     'Validate page fetches GET /datasets/{id}/merge-plan and renders:',
     ['Schema table: 8 columns with type, nulls, distinct, avg_length, classification dropdown',
      'Merge proposal: Single file — no merge needed, 99% confidence (green badge)',
      'Exclude checkboxes on every row',
      'Reject & start over button + Confirm & proceed to cleaning button']),
    ('Step 4 — User Reviews and Confirms HITL #1',
     'User can optionally: exclude columns, override classification, change strategy to JOIN/UNION. Then clicks Confirm.',
     ['POST /merge-plan/decision with approved: true and all overrides',
      'Redirect to /clean/{id}']),
    ('Step 5 — Cleaning Plan Loads (with polling)',
     'Cleaning plan page starts polling every 3 seconds. Backend cleaning plan agent runs for ~5-10 seconds.',
     ['GET /cleaning-plan returns 409 until ready',
      'Once ready, poller stops and 4 steps render']),
    ('Step 6 — HITL #2 Cleaning Plan Review',
     'User sees 4 numbered steps from actual test:',
     ['Step 1: Fix data type — admission_date — 95% (green, pre-checked)',
      'Step 2: Fix data type — discharge_date — 95% (green, pre-checked)',
      'Step 3: Fix data type — readmitted — 90% (green, pre-checked)',
      'Step 4: Fill missing values — notes — 85% (yellow, pre-checked)',
      'All 4 pre-checked (all ≥ 0.70 threshold)',
      'HITL banner: "4 of 4 steps approved"',
      'Submit button: "Submit 4 approved steps"']),
    ('Step 7 — User Submits HITL #2',
     'User clicks Submit. POST /cleaning-plan/decision fires with approved_step_ids: [1,2,3,4]. Backend triggers cleaning executor.',
     ['Next step: redirect to /intent/{id} — intent capture page (not yet built)']),
]

for title, desc, bullets in steps:
    add_heading(title, 2)
    add_para(desc, size=10)
    for b in bullets:
        add_bullet(b)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 13 — KNOWN LIMITATIONS
# ══════════════════════════════════════════════════════════════════════════════
add_heading('13. Known Limitations & Future Work', 1, ACCENT)

add_heading('Current Limitations', 2)
add_table(
    ['Item', 'Current Behaviour', 'Phase 2 Fix'],
    [
        ['Date column classification', 'Date strings (e.g. "2024-02-01") classify as textual because the classifier only tries float() parsing — no date detection. User can override in HITL #1.', 'Add datetime.fromisoformat() detection'],
        ['Polling timeout', 'Cleaning plan poller runs indefinitely if backend fails silently', 'Add max attempts (e.g. 40×3s = 2 min) then show error'],
        ['No HITL #2 reject path', 'No "Reject all & start over" button on cleaning plan page', 'Add reject button posting approved_step_ids: []'],
        ['Step modifications', 'step_modifications field is sent as {} — no UI for per-step overrides yet', 'Build step-level override inputs'],
        ['Intent page',       '/intent/{id} page does not exist yet — redirect after HITL #2 hits 404', 'Build HITL #3 intent capture page'],
        ['Dashboard page',    'Not built yet', 'Build dashboard generation page'],
    ]
)

add_heading('Pending Next Tasks', 2)
for t in [
    'Build HITL #3 intent capture page (/intent/[id]) — free-text question input with domain-tuned suggestion chips',
    'Build dashboard generation page — Vega-Lite charts + KPI cards + narrative',
    'Build insights display with domain-flavoured narrative and recommended next action',
    'Build Admin UI — user management, LLM config, domain pack viewer, audit log',
    'Add polling timeout and error state to cleaning plan page',
    'Add "Reject all & start over" button to HITL #2',
    'End-to-end integration tests for all three HITL checkpoints',
]:
    add_bullet(t)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 14 — INTERVIEW QUICK REFERENCE
# ══════════════════════════════════════════════════════════════════════════════
doc.add_page_break()
add_heading('14. Interview Quick Reference', 1, ACCENT)
add_para(
    'Key talking points that demonstrate technical depth and design thinking.',
    size=10, italic=True
)

add_heading('Design Decisions You Can Discuss', 2)
qas = [
    ('Why use polling instead of WebSockets for the cleaning plan?',
     'For Phase 1 with FastAPI BackgroundTasks and a small user base, short-interval polling (3s) is simpler to implement, requires no extra infrastructure, and is easy to reason about. WebSockets would be the right call at scale (Phase 2 with dedicated worker pools), but polling avoids the complexity of connection management and reconnection logic for now.'),
    ('Why useRef instead of useState for the polling interval ID?',
     'setInterval returns a numeric ID that needs to survive across re-renders without triggering them. useState would cause a re-render every time the interval is updated; useRef provides a stable mutable container that persists without re-rendering.'),
    ('Why reorder the classification conditions (textual before low-cardinality)?',
     'The original order had a subtle bug: small datasets trivially have distinct_count ≤ 50 for almost every column, so the low-cardinality branch fired before the textual check was ever evaluated. The fix reflects the business intent: textual classification (long text or high cardinality relative to dataset size) should take priority over the structural low-cardinality check.'),
    ('How does the merge profile now reflect all files combined?',
     'The propose_merge_plan function was extended with an optional all_rows parameter. For UNION strategy (same schema across files), we now call profile_columns(all_rows) over the complete concatenated row set instead of just the first file\'s rows. The parameter is optional with a None default for backward compatibility with single-file paths in the supervisor.'),
    ('Why does the frontend type system matter so much?',
     'TypeScript types describe the shape the developer expects — but the actual data comes from the API at runtime. If types don\'t match the backend Pydantic schemas, the code compiles cleanly but crashes at runtime (e.g. "Cannot read properties of undefined"). Keeping types in sync with backend schemas is a discipline requirement, not just a "nice to have".'),
    ('Why afterFiles and not beforeFiles in next.config.js?',
     'beforeFiles (the default for array-form rewrites) proxies requests to the backend before Next.js checks local Route Handlers, effectively hiding any local /api/v1/ routes. afterFiles runs after local routes are checked, so local Route Handlers take precedence — the rewrite only fires for paths that have no local handler.'),
]
for q, a in qas:
    p = doc.add_paragraph()
    p.paragraph_format.space_after  = Pt(3)
    p.paragraph_format.space_before = Pt(8)
    r = p.add_run(f'Q: {q}')
    r.bold = True
    r.font.size = Pt(10)
    r.font.color.rgb = ACCENT
    a_para = doc.add_paragraph()
    a_para.paragraph_format.space_after = Pt(6)
    ar = a_para.add_run(f'A: {a}')
    ar.font.size = Pt(10)

# ── Save ──────────────────────────────────────────────────────────────────────
output_path = r'C:\Users\PriyankaKoujalagi\Documents\EURON\DataMindAI\PROJECT-9-DataMind-AI\docs\DataMindAI_HITL_Reference.docx'
doc.save(output_path)
print(f'Saved: {output_path}')
