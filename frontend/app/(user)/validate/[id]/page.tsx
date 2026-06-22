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
  const [typeOverrides, setTypeOverrides] = useState<Record<string, string>>({})
  const [excludedColumns, setExcludedColumns] = useState<string[]>([])
  const [strategy, setStrategy] = useState<string | null>(null)
  const [joinKey, setJoinKey] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.get(`/datasets/${id}/merge-plan`).then((r) => {
      setPlan(r.data)
      setStrategy(r.data.strategy)
      setJoinKey(r.data.join_key ?? null)
    })
  }, [id])

  const handleStrategyChange = (next: string) => {
    setStrategy(next)
    if (next !== 'join') setJoinKey(null)
  }

  const submitDecision = async (approved: boolean) => {
    if (!plan) return
    setSaving(true)
    setError(null)
    try {
      await api.post(`/datasets/${id}/merge-plan/decision`, {
        approved,
        merge_strategy_override: strategy !== plan.strategy ? strategy : null,
        join_key_override: joinKey,
        excluded_columns: excludedColumns,
        type_routing_overrides: typeOverrides,
      })
      router.push(approved ? `/clean/${id}` : '/')
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Something went wrong. Please try again.')
      setSaving(false)
    }
  }

  if (!plan) return <div className='p-8'>Loading schema…</div>
  return (
    <div>
      <h1 className='text-xl font-semibold mb-1'>Schema & merge validation</h1>
      <p className='text-sm text-slate-500 mb-4'>Review inferred schema, column classification, and the proposed merge plan.</p>
      <HitlBanner checkpoint='#1' detail={`${plan.column_profiles.length} columns`} />
      <div className='mb-4'>
        <SchemaTable
          columns={plan.column_profiles}
          excludedColumns={excludedColumns}
          onClassificationChange={(col, classification) =>
            setTypeOverrides((prev) => ({ ...prev, [col]: classification }))
          }
          onExcludeToggle={(col, excluded) =>
            setExcludedColumns((prev) =>
              excluded ? [...prev, col] : prev.filter((c) => c !== col)
            )
          }
        />
      </div>
      <MergeProposal
        plan={plan}
        strategy={strategy ?? plan.strategy}
        joinKey={joinKey}
        onStrategyChange={handleStrategyChange}
        onJoinKeyChange={setJoinKey}
      />
      {error && (
        <p className='mt-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2'>{error}</p>
      )}
      <div className='flex gap-2 mt-4'>
        <button
          onClick={() => submitDecision(false)}
          disabled={saving}
          className='btn-outline text-red-600 border-red-200 hover:bg-red-50'
        >
          Reject & start over
        </button>
        <button
          onClick={() => submitDecision(true)}
          disabled={saving}
          className='btn-primary'
        >
          {saving ? 'Submitting…' : 'Confirm & proceed to cleaning'}
        </button>
      </div>
    </div>
  )
}
