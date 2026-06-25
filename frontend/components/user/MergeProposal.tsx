"use client"
import React from 'react'
import { GitMerge } from 'lucide-react'
import type { MergePlan } from '@/types/pipeline'

const STRATEGY_LABEL: Record<string, string> = {
  single:   'Single file — no merge needed',
  union:    'UNION — stack rows from all files',
  join:     'JOIN — combine files on a shared key',
  separate: 'Separate — keep files independent',
}

function confidenceBadge(score: number) {
  if (score >= 0.9) return 'bg-green-100 text-green-700 border border-green-200'
  if (score >= 0.7) return 'bg-yellow-100 text-yellow-700 border border-yellow-200'
  if (score >= 0.5) return 'bg-orange-100 text-orange-700 border border-orange-200'
  return 'bg-red-100 text-red-700 border border-red-200'
}

export function MergeProposal({
  plan,
  strategy,
  joinKey,
  onStrategyChange,
  onJoinKeyChange,
}: {
  plan: MergePlan
  strategy: string
  joinKey: string | null
  onStrategyChange?: (strategy: string) => void
  onJoinKeyChange?: (joinKey: string | null) => void
}) {
  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GitMerge className="h-4 w-4 text-slate-500" />
          <h3 className="text-sm font-semibold text-slate-800">Merge proposal</h3>
        </div>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${confidenceBadge(plan.confidence)}`}>
          {Math.round(plan.confidence * 100)}% confidence
        </span>
      </div>

      {/* Strategy row */}
      <div className="flex items-center gap-3">
        <label className="w-20 shrink-0 text-xs font-medium text-slate-500">Strategy</label>
        <select
          value={strategy}
          onChange={(e) => onStrategyChange?.(e.target.value)}
          className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
        >
          {Object.entries(STRATEGY_LABEL).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
        {strategy !== plan.strategy && (
          <span className="text-xs text-slate-400 whitespace-nowrap">
            Recommended: {STRATEGY_LABEL[plan.strategy] ?? plan.strategy}
          </span>
        )}
      </div>

      {/* Join key row — only when JOIN is selected */}
      {strategy === 'join' && (
        <div className="flex items-center gap-3">
          <label className="w-20 shrink-0 text-xs font-medium text-slate-500">Merge key</label>
          <select
            value={joinKey ?? ''}
            onChange={(e) => onJoinKeyChange?.(e.target.value || null)}
            className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
          >
            <option value="">— select key column —</option>
            {plan.column_profiles.map((c) => (
              <option key={c.name} value={c.name}>{c.name}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}
