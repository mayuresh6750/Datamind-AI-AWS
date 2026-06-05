"use client"
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { SchemaTable } from '@/components/user/SchemaTable'
import { MergeProposal } from '@/components/user/MergeProposal'
import { HitlBanner } from '@/components/shared/HitlBanner'
import type { MergePlan } from '@/types/pipeline'

export default function ValidatePage() {
  const { id } = useParams() as { id: string }
  const router = useRouter()
  const [plan, setPlan] = useState<MergePlan | null>(null)
  const [decision, setDecision] = useState<Partial<MergePlan>>({})
  const [saving, setSaving] = useState(false)
  useEffect(() => {
    api.get(`/datasets/${id}/merge-plan`).then((r) => setPlan(r.data))
  }, [id])
  const handleConfirm = async () => {
    setSaving(true)
    await api.post(`/datasets/${id}/merge-plan/decision`, {
      approved: true,
      merge_strategy: decision.merge_strategy ?? plan?.merge_strategy,
      merge_key_column: decision.merge_key_column ?? plan?.merge_key_column,
      column_routing: decision.column_routing ?? plan?.column_routing,
    })
    setSaving(false)
    router.push(`/clean/${id}`)
  }
  if (!plan) return <div className='p-8'>Loading schema…</div>
  return (
    <div>
      <h1 className='text-xl font-semibold mb-1'>Schema & merge validation</h1>
      <p className='text-sm text-slate-500 mb-4'>Review inferred schema, column routing, and the proposed merge plan.</p>
      <HitlBanner checkpoint='#1' detail={`${plan.files.length} files`} />
      <div className='grid grid-cols-2 gap-3 mb-4'>
        {plan.files.map((f) => (
            <SchemaTable key={f.filename} file={f} onRouteChange={(col, route) => setDecision(d => ({ ...d, column_routing: { ...(d.column_routing || {}), [col]: route as import('@/types/pipeline').ColumnRouting } }))} />
        ))}
      </div>
      <MergeProposal plan={plan} onChange={(p) => setDecision((d) => ({ ...d, ...p }))} />
      <div className='flex gap-2 mt-4'>
        <button onClick={() => router.back()} className='btn-outline'>Back</button>
        <button onClick={handleConfirm} disabled={saving} className='btn-primary'>{saving ? 'Confirming…' : 'Confirm & proceed to cleaning'}</button>
      </div>
    </div>
  )
}
