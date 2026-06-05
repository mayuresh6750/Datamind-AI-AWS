"use client"
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { submitCleaningDecisions, getCleaningPlan } from '@/lib/pipelineApi'
import type { CleaningPlan, CleaningAction } from '@/types/pipeline'

export default function CleaningPage() {
  const { id } = useParams() as { id: string }
  const router = useRouter()
  const [plan, setPlan] = useState<CleaningPlan | null>(null)
  const [approved, setApproved] = useState<Record<string, boolean>>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    getCleaningPlan(id).then((r) => setPlan(r.data)).catch(() => {})
  }, [id])

  function colorFor(conf: number) {
    if (conf >= 0.9) return 'bg-green-100 text-green-800'
    if (conf >= 0.7) return 'bg-yellow-100 text-yellow-800'
    if (conf >= 0.5) return 'bg-orange-100 text-orange-800'
    return 'bg-red-100 text-red-800'
  }

  const toggle = (a: CleaningAction) => {
    setApproved((s) => ({ ...s, [a.id]: !s[a.id] }))
  }

  const handleSubmit = async () => {
    if (!plan) return
    setSaving(true)
    const decisions = plan.actions.map((a) => ({ step_id: a.id, status: !!approved[a.id] ? 'approved' : 'rejected', override: null }))
    await submitCleaningDecisions(id, decisions as any)
    setSaving(false)
    router.push('/app')
  }

  if (!plan) return <div className='p-8'>Loading cleaning plan…</div>
  return (
    <div>
      <h1 className='text-xl font-semibold mb-1'>Cleaning plan review</h1>
      <p className='text-sm text-slate-500 mb-4'>Review the proposed cleaning steps and approve or reject them.</p>
      <div className='space-y-3'>
        {plan.actions.map((a, i) => (
          <div key={a.id} className='border rounded p-3 flex items-start gap-3'>
            <div className='w-8 text-sm font-medium'>{i + 1}.</div>
            <div className='flex-1'>
              <div className='flex items-center gap-3'>
                <div className={`px-2 py-1 rounded text-xs font-medium ${colorFor(a.confidence)}`}>{Math.round(a.confidence * 100)}%</div>
                <div className='font-semibold'>{a.title}</div>
              </div>
              <p className='text-sm text-slate-600 mt-1'>{a.rationale}</p>
              <p className='text-xs text-muted-foreground mt-2'>Rows affected: {a.rows_affected}</p>
            </div>
            <div className='flex flex-col items-end gap-2'>
              <label className='text-sm'><input type='checkbox' checked={!!approved[a.id]} onChange={() => toggle(a)} /> Approve</label>
            </div>
          </div>
        ))}
      </div>
      <div className='flex gap-2 mt-4'>
        <button onClick={() => router.back()} className='btn-outline'>Back</button>
        <button onClick={handleSubmit} disabled={saving} className='btn-primary'>{saving ? 'Submitting…' : 'Submit decisions'}</button>
      </div>
    </div>
  )
}
