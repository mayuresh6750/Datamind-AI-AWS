"use client"
import { useEffect, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { getDashboard } from '@/lib/pipelineApi'
import { JobProgressBar } from '@/components/shared/JobPoller'
import { KPICard } from '@/components/shared/KPICard'
import { ChartCard } from '@/components/shared/ChartCard'
import type { DashboardSpec } from '@/types/pipeline'

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { id } = useParams() as { id: string }
  const searchParams = useSearchParams()
  const jobId = searchParams.get('job')
  const router = useRouter()

  const [polling, setPolling] = useState(!!jobId)
  const [dashboard, setDashboard] = useState<DashboardSpec | null>(null)
  const [error, setError] = useState<string | null>(null)

  // If no job_id, fetch the already-cached dashboard straight away
  useEffect(() => {
    if (jobId) return
    getDashboard(id)
      .then(setDashboard)
      .catch((err: any) => setError(err?.response?.data?.detail ?? 'Could not load dashboard.'))
  }, [id, jobId])

  // ── Loading state: show progress bar while job runs ───────────────────────
  if (polling) {
    return (
      <div className='max-w-md space-y-4 py-8'>
        <h1 className='text-lg font-semibold text-slate-800'>Running analysis</h1>
        <p className='text-sm text-slate-500'>Building your dashboard — this takes about 30 seconds…</p>
        <JobProgressBar
          jobId={jobId}
          label='Analysing data'
          terminalSteps={['dashboard_ready']}
          onComplete={() => {
            setPolling(false)
            getDashboard(id)
              .then(setDashboard)
              .catch((err: any) => setError(err?.response?.data?.detail ?? 'Could not load dashboard.'))
          }}
          onFailed={(err) => { setPolling(false); setError(err) }}
        />
      </div>
    )
  }

  // ── Fetching state (no job, but dashboard not loaded yet) ─────────────────
  if (!dashboard && !error) {
    return (
      <div className='p-8 flex items-center gap-3 text-slate-500 text-sm'>
        <svg className='animate-spin h-4 w-4 text-blue-600 shrink-0' fill='none' viewBox='0 0 24 24'>
          <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4' />
          <path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8v8z' />
        </svg>
        Loading dashboard…
      </div>
    )
  }

  // ── Error state ──────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className='max-w-lg p-8'>
        <p className='text-sm text-red-600 bg-red-50 border border-red-200 rounded px-4 py-3'>{error}</p>
        <button onClick={() => router.back()} className='btn-outline mt-4'>Go back</button>
      </div>
    )
  }

  // ── Dashboard ────────────────────────────────────────────────────────────
  return (
    <div className='max-w-5xl space-y-8'>
      <div className='flex items-center justify-between'>
        <h1 className='text-xl font-semibold text-slate-900'>Dashboard</h1>
        <button onClick={() => router.push(`/intent/${id}`)} className='btn-outline text-sm'>
          Ask another question
        </button>
      </div>

      {/* KPI Cards */}
      {dashboard!.kpi_cards.length > 0 && (
        <div className='flex flex-wrap gap-4'>
          {dashboard!.kpi_cards.map((card, i) => (
            <KPICard key={i} {...card} />
          ))}
        </div>
      )}

      {/* Charts */}
      {dashboard!.charts.length > 0 && (
        <div className='grid grid-cols-1 md:grid-cols-2 gap-6'>
          {dashboard!.charts.map((chart, i) => (
            <ChartCard key={i} chart={chart} />
          ))}
        </div>
      )}

      {/* Narrative + recommended action */}
      <div className='rounded-xl border bg-blue-50 px-6 py-5 space-y-3'>
        <p className='text-sm text-slate-700 leading-relaxed'>{dashboard!.narrative}</p>
        <div className='flex items-start gap-2'>
          <span className='text-blue-600 mt-0.5'>→</span>
          <p className='text-sm font-medium text-blue-700'>{dashboard!.recommended_action}</p>
        </div>
      </div>
    </div>
  )
}
