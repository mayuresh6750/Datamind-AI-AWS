"use client"
/**
 * useJobPoller — polls /api/v1/jobs/{jobId} every `interval` ms.
 *
 * Calls onComplete when status === "complete" (or an optional terminal step matches).
 * Calls onFailed  when status === "failed" | "error".
 * Returns live { status, progress, currentStep } for rendering.
 */
import { useEffect, useRef, useState } from 'react'
import { pollJob } from '@/lib/pipelineApi'

interface JobSnapshot {
  status: string
  progress_pct: number | null
  current_step: string | null
  error?: string | null
}

interface UseJobPollerOptions {
  /** Called once when the job reaches "complete" (or a terminal step). */
  onComplete: (job: JobSnapshot) => void
  /** Called once when the job reaches "failed" or "error". */
  onFailed: (error: string) => void
  /**
   * Extra `current_step` values that count as completion besides the default
   * "complete" status check (e.g. "dashboard_ready", "awaiting_hitl_merge").
   */
  terminalSteps?: string[]
  /** Poll interval in ms. Default: 3000. */
  interval?: number
}

export function useJobPoller(
  jobId: string | null,
  { onComplete, onFailed, terminalSteps = [], interval = 3000 }: UseJobPollerOptions
) {
  const [snapshot, setSnapshot] = useState<JobSnapshot>({
    status: 'queued',
    progress_pct: 0,
    current_step: null,
    error: null,
  })
  const pollerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // Keep stable refs so the interval callback doesn't close over stale values
  const onCompleteRef = useRef(onComplete)
  const onFailedRef = useRef(onFailed)
  onCompleteRef.current = onComplete
  onFailedRef.current = onFailed

  useEffect(() => {
    if (!jobId) return

    const stop = () => {
      if (pollerRef.current) { clearInterval(pollerRef.current); pollerRef.current = null }
    }

    const check = async () => {
      try {
        const job: JobSnapshot = await pollJob(jobId)
        setSnapshot(job)

        const failed = job.status === 'failed' || job.status === 'error'
        const complete =
          job.status === 'complete' ||
          (job.current_step !== null && terminalSteps.includes(job.current_step))

        if (failed) {
          stop()
          onFailedRef.current(job.error ?? 'Job failed.')
        } else if (complete) {
          stop()
          onCompleteRef.current(job)
        }
      } catch {
        // transient network error — keep polling
      }
    }

    check()
    pollerRef.current = setInterval(check, interval)
    return stop
  }, [jobId, interval, terminalSteps.join(',')])   // eslint-disable-line react-hooks/exhaustive-deps

  return snapshot
}


// ─── Human-readable step labels ──────────────────────────────────────────────

const STEP_LABELS: Record<string, string> = {
  loading_data: 'Loading data…',
  downloading_files: 'Downloading files…',
  generating_merge_plan: 'Analysing schema…',
  awaiting_hitl_merge: 'Waiting for schema approval',
  generating_cleaning_plan: 'Generating cleaning plan…',
  awaiting_hitl_cleaning: 'Waiting for cleaning approval',
  executing_cleaning: 'Cleaning data…',
  storing_json: 'Saving cleaned data…',
  routing_to_postgresql: 'Routing structured columns…',
  embedding_textual_columns: 'Embedding text columns…',
  ready: 'Ready',
  parsing_intent: 'Parsing your question…',
  running_analysis: 'Running analysis…',
  generating_dashboard: 'Building dashboard…',
  dashboard_ready: 'Dashboard ready',
}

function stepLabel(step: string | null): string {
  if (!step) return 'Processing…'
  return STEP_LABELS[step] ?? step.replace(/_/g, ' ')
}


// ─── JobProgressBar component ─────────────────────────────────────────────────

interface JobProgressBarProps {
  /** Job ID to poll. If null, renders nothing. */
  jobId: string | null
  onComplete: (job: JobSnapshot) => void
  onFailed: (error: string) => void
  terminalSteps?: string[]
  /** Short description shown above the bar, e.g. "Preparing dataset". */
  label?: string
}

/**
 * Drop-in progress UI. Renders a labelled progress bar + current step text
 * while polling, then disappears (returns null) once the job completes or
 * errors — letting the parent handle the transition.
 */
export function JobProgressBar({
  jobId,
  onComplete,
  onFailed,
  terminalSteps,
  label = 'Processing',
}: JobProgressBarProps) {
  const { status, progress_pct, current_step } = useJobPoller(jobId, {
    onComplete,
    onFailed,
    terminalSteps,
  })

  if (!jobId) return null

  const pct = progress_pct ?? 0
  const done = status === 'complete'

  return (
    <div className='space-y-2'>
      <div className='flex items-center justify-between text-sm'>
        <span className='font-medium text-slate-700'>{label}</span>
        <span className='text-slate-500 tabular-nums'>{pct}%</span>
      </div>

      {/* Track */}
      <div className='h-2 bg-slate-100 rounded-full overflow-hidden'>
        <div
          className={`h-2 rounded-full transition-all duration-500 ease-out ${
            done ? 'bg-emerald-500' : 'bg-blue-500'
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Step label */}
      <p className='text-xs text-slate-500 flex items-center gap-1.5'>
        {!done && (
          <svg className='animate-spin h-3 w-3 text-blue-500 shrink-0' fill='none' viewBox='0 0 24 24'>
            <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4' />
            <path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8v8z' />
          </svg>
        )}
        {stepLabel(current_step)}
      </p>
    </div>
  )
}
