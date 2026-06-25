"use client"
import { useEffect, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { getCleaningPlan, submitCleaningDecisions } from '@/lib/pipelineApi'
import { HitlBanner } from '@/components/shared/HitlBanner'
import type { CleaningPlan, CleaningStep } from '@/types/pipeline'

const ACTION_LABEL: Record<string, string> = {
  deduplicate: 'Remove duplicates',
  impute: 'Fill missing values',
  coerce_type: 'Fix data type',
  flag_outlier: 'Flag outlier',
}

function confidenceStyle(conf: number): { badge: string; rowBorder: string } {
  if (conf >= 0.9) return { badge: 'bg-green-100 text-green-800', rowBorder: '' }
  if (conf >= 0.7) return { badge: 'bg-yellow-100 text-yellow-800', rowBorder: 'border-l-2 border-yellow-400' }
  if (conf >= 0.5) return { badge: 'bg-orange-100 text-orange-800', rowBorder: 'border-l-2 border-orange-400' }
  return { badge: 'bg-red-100 text-red-800', rowBorder: 'border-l-2 border-red-400' }
}

function initialApproved(steps: CleaningStep[]): Set<number> {
  // Pre-check steps with confidence >= 0.70 per HITL confidence framework
  return new Set(steps.filter((s) => s.confidence >= 0.7).map((s) => s.step_id))
}

export default function CleaningPage() {
  const { id } = useParams() as { id: string }
  const router = useRouter()
  const [plan, setPlan] = useState<CleaningPlan | null>(null)
  const [approvedIds, setApprovedIds] = useState<Set<number>>(new Set())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pollerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const tryFetch = () => {
      getCleaningPlan(id)
        .then((r) => {
          // Plan is ready — stop polling and show it
          if (pollerRef.current) {
            clearInterval(pollerRef.current)
            pollerRef.current = null
          }
          setPlan(r.data)
          setApprovedIds(initialApproved(r.data.steps))
        })
        .catch(() => {
          // 409 = not ready yet; keep polling
        })
    }

    tryFetch()
    pollerRef.current = setInterval(tryFetch, 3000)

    return () => {
      if (pollerRef.current) clearInterval(pollerRef.current)
    }
  }, [id])

  const toggle = (stepId: number) => {
    setApprovedIds((prev) => {
      const next = new Set(prev)
      next.has(stepId) ? next.delete(stepId) : next.add(stepId)
      return next
    })
  }

  const handleSubmit = async () => {
    if (!plan) return
    setSaving(true)
    setError(null)
    try {
      const r = await submitCleaningDecisions(id, {
        approved_step_ids: [...approvedIds],
        step_modifications: {},
      })
      const jobId = r.data?.job_id
      router.push(`/intent/${id}${jobId ? `?job=${jobId}` : ''}`)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Something went wrong. Please try again.')
      setSaving(false)
    }
  }

  if (!plan) {
    return (
      <div className='flex items-center justify-center py-20 gap-2 text-slate-400'>
        <svg className='w-5 h-5 animate-spin' viewBox='0 0 24 24' fill='none'>
          <circle className='opacity-25' cx='12' cy='12' r='10' stroke='currentColor' strokeWidth='4' />
          <path className='opacity-75' fill='currentColor' d='M4 12a8 8 0 018-8v8z' />
        </svg>
        <span className='text-sm'>Generating cleaning plan…</span>
      </div>
    )
  }

  const approvedCount = approvedIds.size
  const totalCount = plan.steps.length

  return (
    <div className='space-y-4'>
      <div>
        <h1 className='page-title'>Cleaning plan review</h1>
        <p className='page-subtitle'>
          Review each proposed cleaning action and approve or reject it before execution.
        </p>
      </div>

      <div className='flex items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-xs text-slate-500 shadow-sm'>
        <span className='font-medium text-slate-700'>{plan.total_rows_before.toLocaleString()} rows</span>
        <span>→ after cleaning →</span>
        <span className='font-medium text-green-700'>{plan.total_rows_after.toLocaleString()} rows</span>
      </div>

      <HitlBanner checkpoint='#2' detail={`${approvedCount} of ${totalCount} steps approved`} />

      <div className='space-y-2.5 mt-2'>
        {plan.steps.map((step, i) => {
          const { badge, rowBorder } = confidenceStyle(step.confidence)
          const isApproved = approvedIds.has(step.step_id)
          return (
            <div
              key={step.step_id}
              className={`rounded-lg border bg-white p-4 flex items-start gap-4 shadow-sm transition-opacity ${rowBorder || 'border-slate-200'} ${!isApproved ? 'opacity-45' : ''}`}
            >
              {/* step number */}
              <div className='w-7 h-7 rounded-full bg-slate-100 flex items-center justify-center text-xs font-semibold text-slate-600 shrink-0'>
                {i + 1}
              </div>

              {/* content */}
              <div className='flex-1 min-w-0'>
                <div className='flex items-center gap-2 flex-wrap'>
                  <span className='text-sm font-semibold text-slate-800'>
                    {ACTION_LABEL[step.action] ?? step.action}
                  </span>
                  {step.column && (
                    <code className='text-xs bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded'>
                      {step.column}
                    </code>
                  )}
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${badge}`}>
                    {Math.round(step.confidence * 100)}% confidence
                  </span>
                </div>
                <p className='text-sm text-slate-500 mt-1'>{step.rationale}</p>
                <div className='flex gap-4 mt-2 text-xs text-slate-400'>
                  <span>Method: <span className='text-slate-600'>{step.method}</span></span>
                  <span>Rows affected: <span className='text-slate-600'>{step.rows_affected.toLocaleString()}</span></span>
                </div>
                {step.confidence < 0.5 && (
                  <p className='text-xs text-red-600 mt-1'>Very low confidence — review carefully before approving.</p>
                )}
              </div>

              {/* approve checkbox */}
              <label className='flex items-center gap-1.5 text-sm text-slate-600 cursor-pointer shrink-0'>
                <input
                  type='checkbox'
                  checked={isApproved}
                  onChange={() => toggle(step.step_id)}
                  className='h-4 w-4 rounded border-slate-300 text-blue-600 cursor-pointer'
                />
                Approve
              </label>
            </div>
          )
        })}
      </div>

      {error && (
        <div className='rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'>{error}</div>
      )}

      <div className='flex items-center justify-between border-t border-slate-100 pt-4'>
        <button onClick={() => router.back()} className='btn-outline'>← Back</button>
        <button onClick={handleSubmit} disabled={saving || approvedCount === 0} className='btn-primary'>
          {saving ? 'Submitting…' : `Apply ${approvedCount} approved step${approvedCount !== 1 ? 's' : ''} →`}
        </button>
      </div>
    </div>
  )
}
