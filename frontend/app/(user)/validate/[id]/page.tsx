"use client"
import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { api } from '@/lib/api'
import { SchemaTable } from '@/components/user/SchemaTable'
import { MergeProposal } from '@/components/user/MergeProposal'
import { HitlBanner } from '@/components/shared/HitlBanner'
import { CheckCircle2, Loader2, RotateCcw } from 'lucide-react'
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

  if (!plan) {
    return (
      <div className="flex items-center justify-center py-20 gap-2 text-slate-400">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span className="text-sm">Loading schema…</span>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Page heading */}
      <div>
        <h1 className="page-title">Schema &amp; merge validation</h1>
        <p className="page-subtitle">
          Review inferred schema, column classification, and the proposed merge plan.
        </p>
      </div>

      <HitlBanner checkpoint='#1' detail={`${plan.column_profiles.length} columns detected`} />

      {/* Schema table card */}
      <div className="page-card">
        <SchemaTable
          columns={plan.column_profiles.map((col) => ({
            ...col,
            classification: typeOverrides[col.name] || col.classification,
          }))}
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

      {/* Merge proposal card */}
      <div className="page-card">
        <MergeProposal
          plan={plan}
          strategy={strategy ?? plan.strategy}
          joinKey={joinKey}
          onStrategyChange={(next) => {
            setStrategy(next)
            if (next !== 'join') setJoinKey(null)
          }}
          onJoinKeyChange={setJoinKey}
        />
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* ── Action row ───────────────────────────────────────────────────────
           REJECT (danger, outlined red) sits left — clearly destructive.
           CONFIRM (primary, solid blue) sits right — clearly the next step.
           Size, icon, and colour make the distinction unmistakable.
      ─────────────────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-100">
        <button
          onClick={() => submitDecision(false)}
          disabled={saving}
          className="btn-danger"
        >
          <RotateCcw className="w-4 h-4" />
          Reject &amp; start over
        </button>

        <button
          onClick={() => submitDecision(true)}
          disabled={saving}
          className="btn-primary"
        >
          {saving
            ? <><Loader2 className="w-4 h-4 animate-spin" /> Submitting…</>
            : <><CheckCircle2 className="w-4 h-4" /> Confirm &amp; proceed to cleaning</>
          }
        </button>
      </div>
    </div>
  )
}
