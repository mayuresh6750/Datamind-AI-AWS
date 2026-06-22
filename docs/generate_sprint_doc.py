"""
Generate DataMind AI — Sprint Reference Doc
Covers: Build intent capture page → Test full flow (intent → dashboard)
Run:  python docs/generate_sprint_doc.py
"""
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc = Document()

# ── Page margins ──────────────────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Cm(2.0)
    section.bottom_margin = Cm(2.0)
    section.left_margin   = Cm(2.5)
    section.right_margin  = Cm(2.5)

# ── Style helpers ─────────────────────────────────────────────────────────────
ACCENT = RGBColor(0x1E, 0x40, 0xAF)
GREEN  = RGBColor(0x16, 0x65, 0x34)
RED    = RGBColor(0x99, 0x17, 0x17)
GRAY   = RGBColor(0x37, 0x41, 0x51)
ORANGE = RGBColor(0xC2, 0x57, 0x00)

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

def add_code_block(lines: list, label: str = ''):
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

def add_before_after(before_lines, after_lines,
                     before_label='BEFORE (buggy)', after_label='AFTER (fixed)'):
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

def file_tag(path: str):
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

def add_note(text: str, color=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after  = Pt(6)
    p.paragraph_format.space_before = Pt(2)
    r = p.add_run(text)
    r.italic = True
    r.font.size = Pt(9.5)
    r.font.color.rgb = color or GRAY

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
rs = sub.add_run('Sprint Reference: Intent Capture → Dashboard\nTechnical & Functional Reference Guide')
rs.bold = True
rs.font.size = Pt(16)
rs.font.color.rgb = GRAY

doc.add_paragraph().paragraph_format.space_after = Pt(20)

meta = doc.add_paragraph()
meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
meta.add_run('Branch: Priyanka-K/feat-backend   |   Date: 2026-06-16').font.size = Pt(10)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# TABLE OF CONTENTS (manual)
# ══════════════════════════════════════════════════════════════════════════════
add_heading('Contents', 1, ACCENT)
toc_entries = [
    ('1', 'Sprint Scope & Architecture'),
    ('2', 'Task 1: Intent Capture Page (HITL #3)'),
    ('3', 'Task 2: Job Polling Component (useJobPoller + JobProgressBar)'),
    ('4', 'Task 3: KPI Card Component'),
    ('5', 'Task 4: Chart Components (Recharts)'),
    ('6', 'Task 5: Dashboard Page'),
    ('7', 'Task 6: Dashboard GET Endpoint'),
    ('8', 'Bug Fix 1 — Vector Search SQL Syntax Error'),
    ('9', 'Bug Fix 2 — Heuristic SQL Textual Columns in GROUP BY'),
    ('10', 'Bug Fix 3 — Login Redirect to Non-Existent /admin/health'),
    ('11', 'Bug Fix 4 — Stale VegaLiteSpec TypeScript Error'),
    ('12', 'Bug Fix 5 — Dashboard Page 404 on Analyse Click'),
    ('13', 'End-to-End Test Results'),
    ('14', 'Known Limitations'),
    ('15', 'Interview Quick Reference'),
]
for num, title in toc_entries:
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
# SECTION 1 — SPRINT SCOPE
# ══════════════════════════════════════════════════════════════════════════════
add_heading('1. Sprint Scope & Architecture', 1, ACCENT)
add_para(
    'This document covers the full sprint that implemented the second half of the DataMind AI '
    'Phase 1 pipeline: from intent capture (HITL #3) through analysis, dashboard generation, '
    'and end-to-end testing. The sprint delivered five new frontend pages/components, one new '
    'backend endpoint, and fixed five bugs discovered during integration testing.',
    size=10, space_after=8
)

add_heading('Sprint Tasks Completed', 2)
add_table(
    ['#', 'Task', 'Type', 'Files Changed'],
    [
        ['T1', 'Build intent capture page — free text + domain suggestion chips', 'Frontend Feature', 'frontend/app/(user)/intent/[id]/page.tsx'],
        ['T2', 'Build job polling component — reusable useJobPoller hook + JobProgressBar', 'Frontend Feature', 'frontend/components/shared/JobPoller.tsx'],
        ['T3', 'Build KPI card component — label, value, change, change_pct with arrows', 'Frontend Feature', 'frontend/components/shared/KPICard.tsx'],
        ['T4', 'Build chart components using Recharts — LineChart, BarChart, TableView', 'Frontend Feature', 'frontend/components/shared/ChartCard.tsx'],
        ['T5', 'Build dashboard page — KPI cards + charts + narrative + recommended action', 'Frontend Feature', 'frontend/app/(user)/dashboard/[id]/page.tsx'],
        ['T6', 'Fetch dashboard — GET /dashboards/{dataset_id}', 'Confirmed Working', 'backend/app/routers/dashboards.py'],
        ['B1', 'Fix vector search SQL syntax error (asyncpg + pgvector)', 'Backend Bug Fix', 'backend/app/agents/analysis.py'],
        ['B2', 'Fix heuristic SQL — textual columns in GROUP BY', 'Backend Bug Fix', 'backend/app/agents/analysis.py'],
        ['B3', 'Fix login redirect to non-existent /admin/health', 'Frontend Bug Fix', 'frontend/app/(auth)/login/page.tsx'],
        ['B4', 'Remove stale VegaLiteSpec type + file', 'Frontend Bug Fix', 'frontend/types/pipeline.ts, components/user/ChartCard.tsx'],
        ['B5', 'Fix 404 on Analyse click (missing dashboard route)', 'Frontend Bug Fix', 'frontend/app/(user)/dashboard/[id]/page.tsx (created)'],
    ]
)

add_heading('End-to-End Pipeline (after this sprint)', 2)
add_code_block([
    'Login → /                           (upload page)',
    '↓ upload CSV/XLSX/JSON/Parquet',
    '→ Ingestion Agent → HITL #1 /validate/{id}',
    '↓ user approves schema',
    '→ Cleaning Plan Agent → HITL #2 /clean/{id}',
    '↓ user approves cleaning steps',
    '→ Cleaning Executor → /intent/{id}    ← NEW this sprint',
    '↓ user submits analysis question',
    '→ Intent Agent → Analysis Agent → Dashboard Agent → Insights Agent',
    '→ Dashboard /dashboard/{id}            ← NEW this sprint',
    '↓ KPI cards + bar/line charts + narrative + recommended action',
], 'Full pipeline flow (Phase 1 complete)')

add_heading('New TypeScript Types Added (frontend/types/pipeline.ts)', 2)
add_code_block([
    'export interface KPICard {',
    '  label: string',
    '  value: string',
    '  change?: string | null         // e.g. "+$12k" — display string',
    '  change_pct?: number | null     // e.g. 12.5 — used for arrow direction',
    '}',
    '',
    'export interface ChartSpec {',
    '  chart_type: "bar" | "line" | "table"',
    '  title: string',
    '  data: Record<string, any>[]    // actual data rows for the chart',
    '  x_field: string                // key in data[] to use as X axis',
    '  y_field: string                // key in data[] to use as Y axis',
    '  color_field?: string | null    // optional series grouping key',
    '}',
    '',
    'export interface DashboardSpec {',
    '  kpi_cards: KPICard[]',
    '  charts: ChartSpec[]',
    '  narrative: string              // domain-flavoured insight paragraph',
    '  recommended_action: string     // one-line call to action',
    '}',
], 'frontend/types/pipeline.ts — DashboardSpec (matches backend Pydantic model)')

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — INTENT CAPTURE PAGE
# ══════════════════════════════════════════════════════════════════════════════
add_heading('2. Task 1: Intent Capture Page (HITL #3)', 1, ACCENT)
file_tag('frontend/app/(user)/intent/[id]/page.tsx')

add_para(
    'HITL #3 is where the user tells the system what they want to learn from their data. '
    'The page provides a free-text textarea and a set of domain-tuned suggestion chips. '
    'It also handles an optional job polling state: if the user arrives from HITL #2 and the '
    'cleaning executor is still running, the page shows a progress bar and waits before displaying '
    'the question form.',
    size=10
)

add_heading('Two Entry Points', 2)
add_table(
    ['Entry Point', 'URL Pattern', 'Behaviour'],
    [
        ['From HITL #2 (cleaning just submitted)',
         '/intent/{id}?job={jobId}',
         'Shows JobProgressBar while cleaning executor runs. When complete, hides progress bar and shows intent form.'],
        ['Direct navigation (data already clean)',
         '/intent/{id}  (no ?job param)',
         'Shows intent form immediately — no polling needed.'],
    ]
)

add_heading('Domain Suggestion Chips', 2)
add_para(
    'Each domain has 5 domain-specific pre-written questions. The active domain is read from Zustand '
    'auth store (user profile). Clicking a chip sets the textarea value. The selected chip gets a '
    'blue filled style to indicate selection.',
    size=10
)
add_table(
    ['Domain', 'Sample Chips'],
    [
        ['Finance',     'What is my monthly recurring revenue trend? / Show gross margin by product / What is the customer churn rate?'],
        ['Healthcare',  'What is the average length of stay by diagnosis? / What is the readmission rate for the past quarter? / Which diagnoses have the highest episode counts?'],
        ['Retail',      'What is the average order value by channel? / Which SKUs have the highest margin? / What is the return rate by product category?'],
        ['Marketing',   'What is the customer acquisition cost by channel? / Show CTR and CPA trends by campaign / What is the LTV to CAC ratio?'],
        ['Operations',  'What is the average cycle time by process? / Show throughput trends over the past month / Which stages have the highest bottlenecks?'],
        ['Other',       'What are the main trends in this dataset? / Show me the top categories by count / What is the distribution of values over time?'],
    ]
)

add_heading('State Management', 2)
add_table(
    ['State Variable', 'Type', 'Purpose'],
    [
        ['ready',       'boolean', 'True when cleaning is done and intent form should show. Initialised to !jobId.'],
        ['question',    'string',  'Current textarea value (controlled input).'],
        ['submitting',  'boolean', 'True while POST /intent is in progress — disables the submit button.'],
        ['error',       'string | null', 'Backend error message shown below form.'],
    ]
)

add_heading('Submit Flow', 2)
add_code_block([
    '// 1. User clicks "Analyse →" or presses Ctrl+Enter',
    'const handleSubmit = async () => {',
    '  if (!question.trim()) return',
    '  setSubmitting(true)',
    '  try {',
    '    const r = await submitIntent(id, { dataset_id: id, question: question.trim() })',
    '    const intentJobId = r.data?.job_id',
    '    // 2. Navigate to dashboard page with job_id so it can poll',
    '    router.push(`/dashboard/${id}${intentJobId ? `?job=${intentJobId}` : ""}`)',
    '  } catch (err: any) {',
    '    setError(err?.response?.data?.detail ?? "Something went wrong.")',
    '    setSubmitting(false)',
    '  }',
    '}',
], 'Intent submit — lib/pipelineApi.ts → POST /api/v1/datasets/{id}/intent')

add_heading('Keyboard Shortcut', 2)
add_para(
    'The textarea accepts Ctrl+Enter (or Cmd+Enter on Mac) as a keyboard shortcut to submit, '
    'providing power-user convenience without requiring the mouse.',
    size=10
)
add_code_block([
    'onKeyDown={(e) => {',
    '  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit()',
    '}}',
])

add_heading('HITL Banner', 2)
add_para(
    'A shared HitlBanner component appears at the top of the intent form with checkpoint="#3" '
    'and detail="Describe your analysis goal". This gives users visual context that they are at '
    'a HITL gate, consistent with the HITL #1 and #2 pages.',
    size=10
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — JOB POLLING COMPONENT
# ══════════════════════════════════════════════════════════════════════════════
add_heading('3. Task 2: Job Polling Component (useJobPoller + JobProgressBar)', 1, ACCENT)
file_tag('frontend/components/shared/JobPoller.tsx')

add_para(
    'Before this sprint, job polling was implemented inline in each page with manual useRef / '
    'useEffect / setInterval code. This led to code duplication and subtle stale-closure bugs. '
    'The refactor extracted polling into a reusable hook (useJobPoller) and a visual component '
    '(JobProgressBar).',
    size=10
)

add_heading('useJobPoller Hook', 2)
add_para(
    'A custom hook that encapsulates the entire polling lifecycle. It polls every 3 seconds '
    '(configurable), maintains a snapshot of the current job state, and fires callbacks when '
    'the job reaches a terminal state.',
    size=10
)
add_code_block([
    'export function useJobPoller(',
    '  jobId: string | null,',
    '  {',
    '    onComplete,       // called with final job object when done or terminalStep reached',
    '    onFailed,         // called with error string on status "failed" or "error"',
    '    terminalSteps = [],  // extra current_step values that count as "complete"',
    '    interval = 3000,  // polling interval in milliseconds',
    '  }: UseJobPollerOptions',
    ') {',
    '  const [snapshot, setSnapshot] = useState<JobSnapshot>({',
    '    status: "queued",',
    '    progress_pct: 0,',
    '    current_step: null,',
    '  })',
    '  const pollerRef     = useRef<ReturnType<typeof setInterval> | null>(null)',
    '  const onCompleteRef = useRef(onComplete)  // stable ref to avoid stale closures',
    '  const onFailedRef   = useRef(onFailed)',
    '  onCompleteRef.current = onComplete  // always latest',
    '  onFailedRef.current   = onFailed',
    '',
    '  useEffect(() => {',
    '    if (!jobId) return',
    '    const stop = () => {',
    '      if (pollerRef.current) { clearInterval(pollerRef.current); pollerRef.current = null }',
    '    }',
    '    const check = async () => {',
    '      const job = await pollJob(jobId)',
    '      setSnapshot(job)',
    '      if (job.status === "failed" || job.status === "error") {',
    '        stop(); onFailedRef.current(job.error ?? "Pipeline failed.")',
    '      } else if (job.status === "complete" ||',
    '                 terminalSteps.includes(job.current_step)) {',
    '        stop(); onCompleteRef.current(job)',
    '      }',
    '    }',
    '    check()   // immediate first call',
    '    pollerRef.current = setInterval(check, interval)',
    '    return stop   // cleanup on unmount',
    '  }, [jobId, interval, terminalSteps.join(",")])',
    '',
    '  return snapshot',
    '}',
], 'useJobPoller — full implementation')

add_heading('Why useRef for callback refs?', 2)
add_para(
    'If onComplete were used directly inside the setInterval closure, it would capture the function '
    'reference from the first render (stale closure). When the parent component re-renders with new '
    'state, the old closure still holds the old function. By storing onComplete in a ref and always '
    'updating the ref, the interval closure always calls the latest version of the callback.',
    size=10
)
add_code_block([
    '// Stale closure problem (without ref):',
    'const onCompleteOld = () => doSomethingWithOldState()  // captured at effect creation time',
    '',
    '// Solution — always call the ref\'s .current:',
    'const onCompleteRef = useRef(onComplete)',
    'onCompleteRef.current = onComplete   // updated on every render',
    '// Inside interval: onCompleteRef.current(job) — always latest!',
])

add_heading('terminalSteps: Flexible Completion Detection', 2)
add_para(
    'job.status === "complete" alone is not enough — some pipeline stages pause mid-job at HITL '
    'gates. The terminalSteps prop lets callers define additional current_step values that should '
    'stop the poller.',
    size=10
)
add_table(
    ['Page', 'terminalSteps value', 'Why'],
    [
        ['intent/[id]',    '(default []) — no terminalSteps',  'Waits for cleaning executor job.status === "complete"'],
        ['dashboard/[id]', '["dashboard_ready"]',              'Dashboard agent sets current_step = "dashboard_ready" while job may still be "running"'],
    ]
)

add_heading('JobProgressBar Component', 2)
add_para(
    'The visual companion to useJobPoller. Renders a progress bar with percentage, a current step '
    'label (human-readable), and a spinning icon. Accepts the same props as useJobPoller.',
    size=10
)
add_table(
    ['Prop', 'Type', 'Description'],
    [
        ['jobId',         'string | null',    'Job ID to poll. If null, component renders nothing useful.'],
        ['label',         'string',           'Title above the progress bar (e.g. "Cleaning data", "Analysing data").'],
        ['terminalSteps', 'string[]',         'Extra current_step values that count as job completion.'],
        ['onComplete',    '(job) => void',    'Called when done — parent should set polling=false, fetch result.'],
        ['onFailed',      '(err) => void',    'Called on failure — parent should show error.'],
    ]
)
add_code_block([
    '// Human-readable step label map (subset shown)',
    'const STEP_LABELS: Record<string, string> = {',
    '  profiling:              "Detecting file format and profiling columns",',
    '  awaiting_hitl_merge:    "Waiting for schema review",',
    '  cleaning_plan:          "Generating cleaning plan",',
    '  awaiting_hitl_cleaning: "Waiting for cleaning approval",',
    '  executing:              "Executing approved cleaning steps",',
    '  routing_storage:        "Routing data to storage layers",',
    '  intent_analysis:        "Analysing your question",',
    '  generating_sql:         "Generating SQL query",',
    '  running_sql:            "Running SQL against your data",',
    '  vector_search:          "Searching embeddings",',
    '  building_dashboard:     "Building dashboard",',
    '  dashboard_ready:        "Dashboard ready",',
    '}',
], 'Step label map for friendly UI copy')

add_heading('Refactor Applied: intent/[id]/page.tsx', 2)
add_para(
    'Before the refactor, the intent page had 15 lines of manual interval polling. '
    'After the refactor, it uses JobProgressBar directly.',
    size=10
)
add_before_after(
    [
        '// BEFORE — manual polling (15 lines)',
        'const pollerRef = useRef(null)',
        '',
        'useEffect(() => {',
        '  if (!jobId) return',
        '  pollerRef.current = setInterval(async () => {',
        '    const job = await pollJob(jobId)',
        '    if (job.status === "complete") {',
        '      clearInterval(pollerRef.current)',
        '      setReady(true)',
        '    } else if (job.status === "error") {',
        '      clearInterval(pollerRef.current)',
        '      setError(job.error)',
        '      setReady(true)',
        '    }',
        '  }, 3000)',
        '  return () => clearInterval(pollerRef.current)',
        '}, [jobId])',
        '',
        '// ... separate loading UI spread across page',
    ],
    [
        '// AFTER — 8 lines, reads like English',
        '<JobProgressBar',
        '  jobId={jobId}',
        '  label="Cleaning data"',
        '  onComplete={() => setReady(true)}',
        '  onFailed={(err) => { setError(err); setReady(true) }}',
        '/>',
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — KPI CARD COMPONENT
# ══════════════════════════════════════════════════════════════════════════════
add_heading('4. Task 3: KPI Card Component', 1, ACCENT)
file_tag('frontend/components/shared/KPICard.tsx')

add_para(
    'A standalone presentational component that displays a single KPI metric. '
    'It receives a label, value, and optional change information, and renders '
    'a coloured directional indicator (up/down/neutral arrow) based on the change_pct.',
    size=10
)

add_heading('Props', 2)
add_table(
    ['Prop', 'Type', 'Required', 'Description'],
    [
        ['label',      'string',         'Yes', 'Short metric name, e.g. "Avg Length of Stay"'],
        ['value',      'string',         'Yes', 'Formatted metric value, e.g. "4.6 days"'],
        ['change',     'string | null',  'No',  'Human-readable absolute change, e.g. "+1.2 days". Shown in parentheses.'],
        ['change_pct', 'number | null',  'No',  'Percentage change as a number (12.5 = 12.5%). Drives arrow direction and colour.'],
    ]
)

add_heading('Arrow Logic', 2)
add_table(
    ['change_pct value', 'Arrow', 'Color Class',    'Meaning'],
    [
        ['null (not provided)',  '(none shown)',   'n/a',             'No trend information available'],
        ['> 0',                 '▲',              'text-emerald-600', 'Positive change (green)'],
        ['< 0',                 '▼',              'text-red-500',    'Negative change (red)'],
        ['=== 0',               '→',              'text-slate-400',  'No change (neutral grey)'],
    ]
)

add_heading('Component Code', 2)
add_code_block([
    'export function KPICard({ label, value, change, change_pct }: KPICardProps) {',
    '  const hasChange = change_pct != null',
    '',
    '  let arrow: string',
    '  let colorClass: string',
    '  if (!hasChange || change_pct === 0) { arrow = "→"; colorClass = "text-slate-400" }',
    '  else if (change_pct! > 0)           { arrow = "▲"; colorClass = "text-emerald-600" }',
    '  else                                { arrow = "▼"; colorClass = "text-red-500" }',
    '',
    '  return (',
    '    <div className="rounded-xl border bg-white px-5 py-4 shadow-sm flex flex-col gap-1.5 min-w-[150px]">',
    '      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide leading-none">',
    '        {label}',
    '      </p>',
    '      <p className="text-2xl font-bold text-slate-900 leading-tight tabular-nums">',
    '        {value}',
    '      </p>',
    '      {hasChange && (',
    '        <p className={`text-xs font-semibold flex items-center gap-1 ${colorClass}`}>',
    '          <span>{arrow}</span>',
    '          <span>{Math.abs(change_pct!).toFixed(1)}%</span>',
    '          {change && <span className="font-normal text-slate-400">({change})</span>}',
    '        </p>',
    '      )}',
    '    </div>',
    '  )',
    '}',
])

add_heading('Usage in Dashboard Page', 2)
add_code_block([
    '// dashboard/[id]/page.tsx',
    '<div className="flex flex-wrap gap-4">',
    '  {dashboard.kpi_cards.map((card, i) => (',
    '    <KPICard key={i} {...card} />',
    '  ))}',
    '</div>',
])

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — CHART COMPONENTS
# ══════════════════════════════════════════════════════════════════════════════
add_heading('5. Task 4: Chart Components (Recharts)', 1, ACCENT)
file_tag('frontend/components/shared/ChartCard.tsx')

add_para(
    'A single ChartCard component that dispatches to three chart variants based on '
    'the chart_type field in ChartSpec. All variants share a common ChartShell wrapper '
    'and an EmptyState component.',
    size=10
)

add_heading('Chart Variants', 2)
add_table(
    ['chart_type', 'Component', 'When Used'],
    [
        ['"bar"',    'BarChartView',  'Comparing values across categories (default)'],
        ['"line"',   'LineChartView', 'Trends over time or sequential data'],
        ['"table"',  'TableView',     'Raw tabular data; when data doesn\'t suit a chart'],
    ]
)

add_heading('ChartShell — Shared Wrapper', 2)
add_code_block([
    'function ChartShell({ title, children }) {',
    '  return (',
    '    <div className="rounded-xl border bg-white shadow-sm p-4 flex flex-col gap-3">',
    '      <p className="text-sm font-semibold text-slate-700">{title}</p>',
    '      {children}',
    '    </div>',
    '  )',
    '}',
])

add_heading('BarChartView Design Decisions', 2)
for b in [
    'CartesianGrid: horizontal lines only (vertical={false}) — reduces visual noise',
    'X-axis labels truncated at 14 chars with ellipsis to prevent overflow on long category names',
    'Tooltip: rounded corners (borderRadius: 8), light border — matches DataMind card aesthetic',
    'Bar radius [3,3,0,0] — rounded top corners only for a modern card look',
    'maxBarSize={48} — prevents single-category charts from rendering absurdly wide bars',
    'Legend only shown when color_field is present (series grouping case)',
]:
    add_bullet(b)

add_heading('LineChartView Design Decisions', 2)
for b in [
    'dot={{ r: 3 }} — small dots on every data point so users can see discrete values',
    'activeDot={{ r: 5 }} — larger dot on hover for the active tooltip point',
    'strokeWidth={2} — thicker line for readability at small component sizes',
    'Same axis / grid styling as BarChart for visual consistency',
]:
    add_bullet(b)

add_heading('TableView Design Decisions', 2)
for b in [
    'First 50 rows shown; footer "Showing 50 of N rows" when dataset has more',
    'overflow-x-auto for horizontal scroll on narrow screens',
    'Keys derived from Object.keys(data[0]) — works for any data shape',
    'hover:bg-slate-50 on rows for interactive feel',
    'whitespace-nowrap on cells to keep table readable even with long strings',
]:
    add_bullet(b)

add_heading('Public ChartCard Dispatcher', 2)
add_code_block([
    'export function ChartCard({ chart }: { chart: ChartSpec }) {',
    '  const { chart_type, title, data, x_field, y_field, color_field } = chart',
    '',
    '  if (chart_type === "table") return <TableView title={title} data={data} />',
    '  if (chart_type === "line")  return <LineChartView ... />',
    '  return <BarChartView ... />   // default: bar',
    '}',
])

add_heading('Stale File Deleted', 2)
add_para(
    'A stale file frontend/components/user/ChartCard.tsx was deleted. It imported VegaLiteSpec '
    'from @/types/pipeline which was removed when types were refactored. This caused a TypeScript '
    'error: "Module \'@/types/pipeline\' has no exported member \'VegaLiteSpec\'". '
    'The new shared/ChartCard.tsx is the canonical location.',
    size=10, color=RED
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — DASHBOARD PAGE
# ══════════════════════════════════════════════════════════════════════════════
add_heading('6. Task 5: Dashboard Page', 1, ACCENT)
file_tag('frontend/app/(user)/dashboard/[id]/page.tsx')

add_para(
    'The dashboard page is the final stop in the pipeline. It renders the complete '
    'analysis output: KPI cards, charts, and a domain-flavoured narrative with a '
    'recommended next action. It handles two entry modes — arriving with a job_id '
    '(intent just submitted) or directly (cached dashboard).',
    size=10
)

add_heading('Entry Modes', 2)
add_table(
    ['Entry Mode', 'URL', 'Behaviour'],
    [
        ['With job_id',    '/dashboard/{id}?job={jobId}', 'polling = true, shows JobProgressBar for "dashboard_ready" step, then fetches dashboard when done'],
        ['Without job_id', '/dashboard/{id}',             'polling = false, directly fetches GET /dashboards/{id} on mount'],
    ]
)

add_heading('Page State Machine', 2)
add_code_block([
    'State 1: polling === true',
    '  → Shows <JobProgressBar terminalSteps={["dashboard_ready"]} ...>',
    '  → onComplete → setPolling(false) + getDashboard(id).then(setDashboard)',
    '  → onFailed  → setPolling(false) + setError(err)',
    '',
    'State 2: polling === false && !dashboard && !error',
    '  → Shows spinner "Loading dashboard..."',
    '  → (loading getDashboard in background)',
    '',
    'State 3: error !== null',
    '  → Shows red error box with "Go back" button',
    '',
    'State 4: dashboard !== null',
    '  → Renders full dashboard: KPI cards + charts + narrative + action',
])

add_heading('Dashboard Layout', 2)
for b in [
    'Header row: "Dashboard" title + "Ask another question" button → /intent/{id}',
    'KPI Cards: flex-wrap row, each card min-w-[150px], gap-4',
    'Charts: 2-column responsive grid (grid-cols-1 md:grid-cols-2), gap-6',
    'Narrative block: blue-tinted rounded card (bg-blue-50), narrative paragraph + → recommended action',
]:
    add_bullet(b)

add_heading('Bug Fixed During Creation: useState vs useEffect', 2)
add_note(
    'The initial version of the dashboard page incorrectly used useState initialiser for a side effect. '
    'useState(fn) runs fn synchronously during render — not appropriate for async API calls.',
    RED
)
add_before_after(
    [
        '// WRONG — side effect in useState initialiser',
        '// useState(fn) runs synchronously, not for async ops',
        'useState(() => {',
        '  getDashboard(id).then(setDashboard)',
        '})',
    ],
    [
        '// CORRECT — useEffect with dependency array',
        'useEffect(() => {',
        '  if (jobId) return  // skip if we\'re polling',
        '  getDashboard(id)',
        '    .then(setDashboard)',
        '    .catch((err: any) => setError(',
        '      err?.response?.data?.detail ?? "Could not load dashboard."',
        '    ))',
        '}, [id, jobId])',
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — DASHBOARD GET ENDPOINT
# ══════════════════════════════════════════════════════════════════════════════
add_heading('7. Task 6: Dashboard GET Endpoint', 1, ACCENT)
file_tag('backend/app/routers/dashboards.py')

add_para(
    'The dashboard endpoint was already present in the backend from a previous sprint. '
    'This section documents its architecture for reference.',
    size=10
)

add_heading('In-Memory Cache Architecture', 2)
add_para(
    'The backend stores generated dashboards in a module-level dict. This is intentionally simple '
    'for Phase 1 — the cache is process-scoped, meaning a server restart loses all cached dashboards. '
    'Phase 2 will persist DashboardSpec to PostgreSQL or Supabase Storage.',
    size=10
)
add_code_block([
    '# dashboards.py',
    '_dashboard_cache: dict[str, dict] = {}   # dataset_id → DashboardSpec dict',
    '',
    'def cache_dashboard(dataset_id: str, spec: DashboardSpec):',
    '    _dashboard_cache[dataset_id] = spec.model_dump()',
    '',
    '@router.get("/{dataset_id}")',
    'async def get_dashboard(dataset_id: str, user=Depends(get_current_user), db=Depends(get_db)):',
    '    # 1. Ownership check (dataset must belong to requesting user)',
    '    row = await db.execute(select(Dataset).where(',
    '        Dataset.dataset_id == dataset_id,',
    '        Dataset.user_id == user["sub"]',
    '    ))',
    '    if not row.scalars().first():',
    '        raise HTTPException(404, "Dataset not found")',
    '    # 2. Read from in-memory cache',
    '    spec = _dashboard_cache.get(dataset_id)',
    '    if not spec:',
    '        raise HTTPException(404, "Dashboard not generated yet. Run intent first.")',
    '    return spec',
])

add_heading('Frontend API Call', 2)
add_code_block([
    '// frontend/lib/pipelineApi.ts',
    'export const getDashboard = (id: string) =>',
    '  api.get<DashboardSpec>(`/dashboards/${id}`).then(r => r.data)',
])

add_heading('Cache Lifecycle', 2)
add_table(
    ['Event', 'Cache Effect'],
    [
        ['User submits intent question',        'cache_dashboard(dataset_id, spec) called at end of intent_analysis_pipeline — overwrites any previous entry'],
        ['User clicks "Ask another question"',  'New intent submitted → cache entry overwritten with new DashboardSpec'],
        ['Backend server restart',              'Cache cleared — user must re-submit intent to regenerate dashboard'],
        ['Different user\'s dataset_id',        'Ownership check in GET endpoint prevents access — 404 returned'],
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — BUG FIX 1: VECTOR SEARCH SQL
# ══════════════════════════════════════════════════════════════════════════════
add_heading('8. Bug Fix 1 — Vector Search SQL Syntax Error (asyncpg + pgvector)', 1, ACCENT)
file_tag('backend/app/agents/analysis.py → run_textual() and tasks.py → store_embeddings()')

add_heading('Root Cause', 2)
add_para(
    'asyncpg (the async PostgreSQL driver used by SQLAlchemy async) translates named parameters '
    '(:name) to positional parameters ($1, $2, …) before sending the query to PostgreSQL. '
    'The pgvector type cast syntax uses double-colon notation: :embedding::vector.',
    size=10
)
add_para(
    'When asyncpg processes :embedding::vector, it strips :embedding and replaces it with $1 — '
    'but then the remaining ::vector is interpreted as another named parameter starting with a '
    'colon, which causes a syntax error.',
    size=10, color=RED, italic=True
)
add_code_block([
    'Error: syntax error at or near ":"',
    '  Query: ... embedding <=> :embedding::vector ...',
    '  asyncpg sees: :embedding  →  $1  but then sees ::vector as another :name',
])

add_heading('Before / After — run_textual() in analysis.py', 2)
add_before_after(
    [
        '# asyncpg cannot parse :embedding::vector',
        'sql = text("""',
        '    SELECT content, metadata,',
        '      1 - (embedding <=> :embedding::vector) AS similarity',
        '    FROM dataset_embeddings',
        '    WHERE dataset_id = :dataset_id',
        '    ORDER BY embedding <=> :embedding::vector',
        '    LIMIT :top_k',
        '""")',
    ],
    [
        '# Use CAST() syntax — asyncpg handles this correctly',
        'sql = text("""',
        '    SELECT content, metadata,',
        '      1 - (embedding <=> CAST(:embedding AS vector)) AS similarity',
        '    FROM dataset_embeddings',
        '    WHERE dataset_id = :dataset_id',
        '    ORDER BY embedding <=> CAST(:embedding AS vector)',
        '    LIMIT :top_k',
        '""")',
    ]
)

add_heading('Before / After — store_embeddings() in tasks.py', 2)
add_before_after(
    [
        '# Same syntax error on INSERT',
        'await db.execute(text("""',
        '    INSERT INTO dataset_embeddings',
        '      (dataset_id, content, metadata, embedding)',
        '    VALUES',
        '      (:dataset_id, :content, :meta, :emb::vector)',
        '"""), params)',
    ],
    [
        '# Fixed with CAST()',
        'await db.execute(text("""',
        '    INSERT INTO dataset_embeddings',
        '      (dataset_id, content, metadata, embedding)',
        '    VALUES',
        '      (:dataset_id, :content, :meta, CAST(:emb AS vector))',
        '"""), params)',
    ]
)

add_heading('Verification from Logs', 2)
add_code_block([
    '# After the fix, the following log line appeared:',
    '"analysis_vector_search_done hits: 10"',
    '',
    '# This confirms:',
    '#   - The CAST syntax was accepted by asyncpg without syntax error',
    '#   - pgvector returned 10 matching rows via cosine similarity',
    '#   - The embedding was correctly cast to vector type for comparison',
])

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — BUG FIX 2: HEURISTIC SQL
# ══════════════════════════════════════════════════════════════════════════════
add_heading('9. Bug Fix 2 — Heuristic SQL Textual Columns in GROUP BY', 1, ACCENT)
file_tag('backend/app/agents/analysis.py → _heuristic_sql()')

add_heading('Context: When Heuristics Fire', 2)
add_para(
    'The analysis agent calls Google Gemini to generate SQL. When Gemini returns 503 (overloaded) '
    'or 429 (rate limit exceeded), the agent falls back to a heuristic SQL generator. '
    'During this sprint, the Gemini free tier quota (20 requests/day) was exhausted during testing, '
    'so the heuristic fired on every pipeline run.',
    size=10
)

add_heading('Root Cause', 2)
add_para(
    'The intent agent\'s heuristic (_heuristic_parse) returns an AnalysisSpec with two fields: '
    'measures (numeric columns) and dimensions (textual/categorical columns). '
    'The analysis agent\'s _heuristic_sql then tried to GROUP BY the dimensions.',
    size=10
)
add_para(
    'The problem: textual columns (like patient_id, patient_name, diagnosis) are stored in '
    'pgvector — not in the PostgreSQL numeric table. The heuristic SQL ran against the PostgreSQL '
    'table, so referencing textual dimension columns caused "column does not exist" errors.',
    size=10, color=RED, italic=True
)
add_code_block([
    'Error: column "patient_id" does not exist',
    '  Query: SELECT AVG(CAST("length_of_stay_days" AS FLOAT)), "patient_id"',
    '         FROM "dataset_abc123"',
    '         GROUP BY "patient_id"',
    '  Cause: patient_id is textual → stored in pgvector, NOT in this PostgreSQL table',
])

add_heading('Before / After', 2)
add_before_after(
    [
        'def _heuristic_sql(self, spec, table_name):',
        '    measures = spec.measures or []',
        '    dimensions = spec.dimensions or []',
        '    if measures:',
        '        aggs = ", ".join(',
        '            f\'AVG(CAST("{m}" AS FLOAT)) AS "{m}"\'',
        '            for m in measures',
        '        )',
        '        # dimensions = textual cols — NOT in SQL table!',
        '        if dimensions:',
        '            dim_list = ", ".join(f\'"{d}"\' for d in dimensions)',
        '            return (',
        '                f\'SELECT {dim_list}, {aggs}\'',
        '                f\' FROM "{table_name}"\'',
        '                f\' GROUP BY {dim_list}\'  # ← CRASH',
        '                f\' LIMIT 100\'',
        '            )',
        '        return f\'SELECT {aggs} FROM "{table_name}" LIMIT 100\'',
        '    return f\'SELECT * FROM "{table_name}" LIMIT 100\'',
    ],
    [
        'def _heuristic_sql(self, spec, table_name):',
        '    # Only aggregate measures — dimensions are textual',
        '    # and live in pgvector, not in this PostgreSQL table',
        '    if spec.measures:',
        '        aggs = ", ".join(',
        '            f\'AVG(CAST("{m}" AS FLOAT)) AS "{m}"\'',
        '            for m in spec.measures',
        '        )',
        '        return f\'SELECT {aggs} FROM "{table_name}" LIMIT 100\'',
        '    return f\'SELECT * FROM "{table_name}" LIMIT 100\'',
    ]
)

add_heading('Acknowledged Limitation', 2)
add_para(
    'When Gemini is unavailable, the heuristic picks the same numeric column (length_of_stay_days) '
    'regardless of the question text. This means asking "What is average length of stay?" and '
    '"What is the readmission rate?" both produce the same AVG(length_of_stay_days) result. '
    'This is expected behaviour — the heuristic ignores question semantics. '
    'Full question-aware analysis resumes when Gemini quota resets or a paid API key is configured.',
    size=10, color=ORANGE, italic=True
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 10 — BUG FIX 3: LOGIN REDIRECT
# ══════════════════════════════════════════════════════════════════════════════
add_heading('10. Bug Fix 3 — Login Redirect to Non-Existent /admin/health', 1, ACCENT)
file_tag('frontend/app/(auth)/login/page.tsx')

add_heading('Symptom', 2)
add_para(
    'Clicking the login button with valid credentials redirected to http://localhost:3000/admin/health '
    'which returned a Next.js 404 "Page could not be found" error. The user account had the admin role.',
    size=10, color=RED, italic=True
)

add_heading('Root Cause', 2)
add_para(
    'The login page contained a role-based redirect: admin users were sent to /admin/health. '
    'However, the Admin UI page at /admin/health had not been built yet in this sprint. '
    'The URL existed in the old plan but was never implemented.',
    size=10
)

add_before_after(
    [
        '// Role-based redirect to non-existent page',
        'window.location.href =',
        '  body.role === "admin"',
        '    ? "/admin/health"   // ← page does not exist!',
        '    : "/domain"',
    ],
    [
        '// Everyone goes to upload page after login',
        'window.location.href = "/"',
    ]
)

add_heading('Decision', 2)
add_para(
    'The Admin UI is planned but not yet built. The correct interim behaviour is to redirect all '
    'users — regardless of role — to the upload page (/). The admin-specific redirect can be '
    're-added once /admin pages are implemented.',
    size=10
)

add_heading('Related Issue: Stale Zustand Token', 2)
add_para(
    'A second login symptom appeared: navigating to http://localhost:3000 showed the upload page '
    'instead of the login page, even before logging in. Root cause: a stale JWT token remained '
    'in localStorage from a previous session (Zustand persist middleware under key "datamind-auth"). '
    'The user layout read the non-null token and skipped the login redirect. Fix: click the Logout '
    'button which calls clearAuth() and clears the persisted Zustand state.',
    size=10, italic=True
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 11 — BUG FIX 4: STALE VEGATIELITESPEC
# ══════════════════════════════════════════════════════════════════════════════
add_heading('11. Bug Fix 4 — Stale VegaLiteSpec TypeScript Error', 1, ACCENT)

add_heading('Error Message', 2)
add_code_block([
    "TypeScript error TS2305:",
    "Module '\"@/types/pipeline\"' has no exported member 'VegaLiteSpec'.",
    "  at: frontend/components/user/ChartCard.tsx:1:10",
])

add_heading('Root Cause', 2)
add_para(
    'The old types/pipeline.ts contained a VegaLiteSpec type for Vega-Lite chart specs '
    '(the earlier charting approach). When types were refactored to match the backend '
    'DashboardSpec (using ChartSpec instead of VegaLiteSpec), the old type was removed. '
    'However, the file frontend/components/user/ChartCard.tsx was never updated — it still '
    'imported VegaLiteSpec which no longer existed.',
    size=10
)

add_heading('Fix', 2)
add_para(
    'The stale file frontend/components/user/ChartCard.tsx was deleted. '
    'The new canonical implementation is at frontend/components/shared/ChartCard.tsx '
    'which uses ChartSpec (matching the backend). No functionality was lost — the new '
    'file provides the same BarChart/LineChart/Table rendering.',
    size=10
)
add_table(
    ['File', 'Action', 'Reason'],
    [
        ['frontend/components/user/ChartCard.tsx',   'DELETED',  'Stale, used VegaLiteSpec which was removed from types'],
        ['frontend/components/shared/ChartCard.tsx', 'CREATED',  'New canonical chart component, uses ChartSpec'],
        ['frontend/types/pipeline.ts',               'UPDATED',  'VegaLiteSpec removed; KPICard, ChartSpec, DashboardSpec added'],
    ]
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 12 — BUG FIX 5: DASHBOARD 404
# ══════════════════════════════════════════════════════════════════════════════
add_heading('12. Bug Fix 5 — Dashboard Page 404 on Analyse Click', 1, ACCENT)

add_heading('Symptom', 2)
add_para(
    'After submitting the intent question and clicking the "Analyse →" button on the intent page, '
    'the browser navigated to /dashboard/{id}?job={jobId} and immediately showed the Next.js '
    '404 "This page could not be found" error.',
    size=10, color=RED, italic=True
)

add_heading('Root Cause', 2)
add_para(
    'The dashboard route /dashboard/[id] did not exist as a Next.js App Router page. '
    'The intent page was navigating to it correctly (the intent submit backend was working and '
    'returning a job_id, as confirmed by backend logs showing intent_analysis_pipeline_complete), '
    'but there was no page.tsx file at frontend/app/(user)/dashboard/[id]/.',
    size=10
)

add_heading('Fix', 2)
add_para(
    'Created frontend/app/(user)/dashboard/[id]/page.tsx. This is the main page built in Task 5 '
    '(see Section 6). The file implements job polling while the analysis runs, then renders '
    'the full dashboard once the DashboardSpec is available from the backend.',
    size=10
)

add_heading('Backend Was Already Working', 2)
add_para(
    'The backend logs confirmed the full pipeline was running successfully even before the '
    'frontend page existed:',
    size=10
)
add_code_block([
    '# Log evidence (from manual testing session):',
    'intent_analysis_pipeline_started dataset_id=abc123',
    'intent_agent_done question="What is average length of stay?"',
    'analysis_sql_gen_done',
    'analysis_numeric_done rows=1',
    'analysis_vector_search_done hits=10',
    'dashboard_generated kpi_count=1 chart_count=1',
    'intent_analysis_pipeline_complete dataset_id=abc123',
    '',
    '# GET /dashboards/abc123 was also returning HTTP 200 with DashboardSpec',
    '# The only missing piece was the frontend page to display it.',
])

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 13 — END-TO-END TEST RESULTS
# ══════════════════════════════════════════════════════════════════════════════
add_heading('13. End-to-End Test Results', 1, ACCENT)
add_para(
    'Full end-to-end test completed on 2026-06-16 using the healthcare CSV test file '
    'and a live running backend (FastAPI on port 8000) + frontend (Next.js on port 3000). '
    'The Gemini free tier quota was exhausted during this session, so heuristic fallbacks '
    'fired for all LLM agent steps.',
    size=10
)

add_heading('Test Session Flow', 2)
steps = [
    ('Step 1: Login',
     'Navigated to http://localhost:3000/login. Entered credentials. Click Sign in.',
     'Login page submitted to POST /api/v1/auth/login. JWT token stored in Zustand. '
     'Redirect to / (upload page). PASS.'),
    ('Step 2: Domain Selection',
     'Upload page showed domain selection. Selected "Healthcare".',
     'PATCH /api/v1/me/domain with { active_domain: "healthcare" }. Domain saved. PASS.'),
    ('Step 3: File Upload',
     'Dragged test_healthcare.csv onto upload zone.',
     'Presigned URL obtained, file uploaded to Supabase Storage. '
     'POST /api/v1/datasets/{id}/ingest triggered. '
     'Page polled job every 2s. After ~3-4s, redirected to /validate/{id}. PASS.'),
    ('Step 4: HITL #1 Validate',
     'Schema table showed 8 columns. Classifications visible. '
     'Merge strategy: Single (99% confidence, green badge). '
     'Clicked "Confirm & proceed to cleaning".',
     'POST /merge-plan/decision approved=true. '
     'Redirect to /clean/{id}. PASS.'),
    ('Step 5: HITL #2 Cleaning Plan',
     'Cleaning plan page polled every 3s. After ~6s, 4 steps appeared. '
     'All 4 pre-checked (all ≥ 0.70 confidence). '
     'Clicked "Submit 4 approved steps".',
     'POST /cleaning-plan/decision with approved_step_ids: [1,2,3,4]. '
     'Redirect to /intent/{id}?job={jobId}. PASS.'),
    ('Step 6: Intent Page (Cleaning Executor Running)',
     'Intent page showed JobProgressBar "Cleaning data". '
     'After ~5-8s cleaning finished. Intent form appeared.',
     'Cleaning executor pipeline completed successfully. PASS.'),
    ('Step 7: Submit Intent Question',
     'Clicked suggestion chip "What is the average length of stay by diagnosis?". '
     'Clicked "Analyse →".',
     'POST /intent with question text. '
     'Redirect to /dashboard/{id}?job={intentJobId}. PASS.'),
    ('Step 8: Dashboard Rendered',
     'Dashboard page showed JobProgressBar "Analysing data" for ~10-15s. '
     'Then dashboard appeared with:',
     'KPI card: "Avg length_of_stay_days — 4.60". '
     'Bar chart: "length_of_stay_days by patient_id" (heuristic fallback — Gemini quota exhausted). '
     'Narrative and recommended action below chart. PASS.'),
    ('Step 9: Ask Another Question',
     'Clicked "Ask another question". '
     'Navigated to /intent/{id} (no job_id this time). '
     'Typed a custom question manually. '
     'Clicked "Analyse →".',
     'New intent pipeline ran (confirmed by 3 separate intent_analysis_pipeline_complete '
     'log entries with same dataset_id but different timestamps). '
     'Dashboard re-rendered with same heuristic output (expected — Gemini quota exhausted). PASS.'),
]

for step_title, action, outcome in steps:
    add_heading(step_title, 2)
    add_para(f'Action: {action}', size=10, bold=False)
    add_para(f'Outcome: {outcome}', size=10, color=GREEN)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 14 — KNOWN LIMITATIONS
# ══════════════════════════════════════════════════════════════════════════════
add_heading('14. Known Limitations', 1, ACCENT)

add_heading('Gemini Free Tier Quota (20 req/day)', 2)
add_para(
    'The free tier of gemini-3.5-flash allows 20 requests per day per API key. '
    'During testing, the quota was exhausted, causing all four LLM agents (intent, '
    'analysis_sql_gen, dashboard, insights) to fall back to heuristic logic. '
    'The heuristics ignore question text and always produce the same SQL and dashboard '
    'regardless of the user\'s question.',
    size=10
)
add_para(
    'Resolution: Use a paid Gemini API key, or wait 24 hours for the free quota to reset.',
    size=10, italic=True
)

add_heading('In-Memory Dashboard Cache', 2)
add_para(
    'dashboard_cache in dashboards.py is a module-level Python dict. '
    'It is scoped to the server process. Restarting the backend server (uvicorn reload, '
    'Docker restart) clears all cached dashboards. Users must re-submit their intent '
    'question to regenerate the dashboard.',
    size=10
)
add_para(
    'Phase 2 fix: Persist DashboardSpec as JSONB in the pipeline_runs table or in Supabase Storage.',
    size=10, italic=True
)

add_heading('Supabase Storage 403 on datamind-json Bucket', 2)
add_para(
    'The cleaning executor writes cleaned JSON to Supabase Storage bucket "datamind-json". '
    'RLS (Row Level Security) policies on this bucket returned HTTP 403 during some test runs. '
    'The pipeline gracefully falls back to re-parsing the original archive file. '
    'This fallback works correctly but is slower.',
    size=10, color=ORANGE
)
add_para(
    'Root cause not yet investigated. The RLS policies on the datamind-json bucket may need '
    'to be reviewed to allow the service role to write from the backend.',
    size=10, italic=True
)

add_heading('Heuristic SQL — Question-Blind', 2)
add_para(
    'When Gemini is unavailable, the _heuristic_sql function generates SQL by picking '
    'the first numeric column and computing AVG. It does not interpret the user\'s question. '
    'All questions for the same dataset produce identical SQL and identical dashboard output.',
    size=10, color=ORANGE
)

add_heading('Admin UI Not Built', 2)
add_para(
    'The /admin/* routes (user management, LLM config, domain pack viewer, audit log, system health) '
    'are planned for a future sprint. Admin users who log in will reach the upload page '
    '(same as regular users) until the Admin UI is implemented.',
    size=10
)

doc.add_page_break()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 15 — INTERVIEW QUICK REFERENCE
# ══════════════════════════════════════════════════════════════════════════════
add_heading('15. Interview Quick Reference', 1, ACCENT)
add_para(
    'Key technical talking points covering decisions made in this sprint.',
    size=10, italic=True
)

qas = [
    (
        'Why does the job polling hook use useRef for callbacks instead of putting the function directly in the interval closure?',
        'setInterval captures the function reference at the time the effect runs. If the parent component re-renders with new state (e.g., after the first poll tick), the interval closure still holds the old version of the callback — this is the stale closure problem. By storing the callback in a ref and updating ref.current on every render, the interval always calls the latest function. This pattern is idiomatic React for long-lived callbacks inside effects.',
    ),
    (
        'Why can\'t you write :embedding::vector in asyncpg?',
        'asyncpg translates named parameters (:name) to positional parameters ($N) before sending SQL to PostgreSQL. The cast syntax ::vector starts with a colon, which asyncpg interprets as the start of another named parameter. This confuses the parser and produces a syntax error. The fix is to use CAST(:embedding AS vector) — the SQL-standard cast form that asyncpg can parse without ambiguity.',
    ),
    (
        'Why were textual columns in the heuristic SQL GROUP BY wrong?',
        'The DataMind storage architecture routes columns by type: numeric/structured columns go to PostgreSQL, textual/free-text columns go to pgvector. The heuristic SQL ran against the PostgreSQL table (which only has numeric columns). Attempting to GROUP BY textual columns like patient_id caused "column does not exist" errors because those columns simply are not in that table.',
    ),
    (
        'Why is the dashboard cache in-memory rather than in the database?',
        'For Phase 1 with a small user base and FastAPI BackgroundTasks (single-process), an in-memory dict is the simplest correct solution. It avoids adding a database write at the end of every pipeline and keeps the architecture minimal. The trade-off — losing dashboards on server restart — is acceptable for an internal beta. Phase 2 will persist DashboardSpec as JSONB in the pipeline_runs table.',
    ),
    (
        'How does the dashboard page handle the job not being done when the user arrives?',
        'The intent page passes the job_id as a URL query parameter when redirecting: /dashboard/{id}?job={jobId}. The dashboard page reads this with useSearchParams(). If job_id is present, it renders a JobProgressBar that polls until the dashboard_ready step is reached. Once complete, the progress bar disappears and the page fetches the dashboard from GET /dashboards/{id}. If no job_id is present (e.g., direct navigation), the page fetches immediately.',
    ),
    (
        'What are the three pieces of evidence that prove the backend pipeline was working before the dashboard page existed?',
        'First, the backend logs showed intent_analysis_pipeline_complete with the dataset_id. Second, GET /dashboards/{id} returned HTTP 200 with a valid DashboardSpec JSON body. Third, the error was a Next.js 404 (client-side routing miss), not a backend 500 — confirming the backend was healthy and the only missing piece was the frontend route.',
    ),
    (
        'What is the difference between job.status and job.current_step?',
        'job.status is the background worker lifecycle: queued, running, complete, or error. job.current_step is the pipeline domain stage: profiling, awaiting_hitl_merge, cleaning_plan, awaiting_hitl_cleaning, executing, etc. These are completely separate fields. A job can have status=running while current_step=awaiting_hitl_merge — the worker thread is alive but the pipeline is paused at a HITL gate. Frontend code must check current_step (not status) to know when to redirect to a HITL review page.',
    ),
    (
        'Why does KPICard use tabular-nums Tailwind class on the value text?',
        'tabular-nums activates OpenType tnum feature, which renders all digits at equal width regardless of which numeral they are. Without this, digits like 1 and 4 have different widths in proportional fonts, causing numbers to visually "jump" when values update (e.g., from 4.6 to 14.6). Tabular nums keeps values stable and scannable, which is important for a KPI dashboard that users compare across cards.',
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
    a_para = doc.add_paragraph()
    a_para.paragraph_format.space_after = Pt(6)
    ar = a_para.add_run(f'A: {a}')
    ar.font.size = Pt(10)

# ── Save ──────────────────────────────────────────────────────────────────────
output_path = (
    r'C:\Users\PriyankaKoujalagi\Documents\EURON\DataMindAI'
    r'\PROJECT-9-DataMind-AI\docs\DataMindAI_Sprint_Intent_Dashboard_Reference.docx'
)
doc.save(output_path)
print(f'Saved: {output_path}')
