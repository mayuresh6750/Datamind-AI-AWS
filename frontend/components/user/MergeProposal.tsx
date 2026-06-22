"use client"
import React from 'react'
import type { MergePlan } from '@/types/pipeline'

const STRATEGY_LABEL: Record<string, string> = {
  single: 'Single file — no merge needed',
  union: 'UNION — stack rows from all files',
  join: 'JOIN — combine files on a shared key',
  separate: 'Separate — keep files independent',
}

const CONFIDENCE_COLOUR = (score: number) => {
  if (score >= 0.9) return 'bg-green-100 text-green-700'
  if (score >= 0.7) return 'bg-yellow-100 text-yellow-700'
  if (score >= 0.5) return 'bg-orange-100 text-orange-700'
  return 'bg-red-100 text-red-700'
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
    <div className='p-4 border rounded-lg space-y-3'>
      <div className='flex items-center justify-between'>
        <h3 className='font-semibold text-slate-800'>Merge proposal</h3>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${CONFIDENCE_COLOUR(plan.confidence)}`}>
          {Math.round(plan.confidence * 100)}% confidence
        </span>
      </div>

      {/* strategy override — defaults to the agent's recommendation */}
      <div className='flex items-center gap-2'>
        <span className='text-xs text-slate-500'>Strategy</span>
        <select
          value={strategy}
          onChange={(e) => onStrategyChange?.(e.target.value)}
          className='text-sm border rounded px-2 py-1 text-slate-800 focus:outline-none focus:ring-1 focus:ring-slate-300'
        >
          {Object.entries(STRATEGY_LABEL).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
        {strategy !== plan.strategy && (
          <span className='text-xs text-slate-400'>(recommended: {STRATEGY_LABEL[plan.strategy] ?? plan.strategy})</span>
        )}
      </div>

      {/* merge key selector — only shown when effective strategy is JOIN */}
      {strategy === 'join' && (
        <div className='flex items-center gap-2'>
          <span className='text-xs text-slate-500'>Merge key</span>
          <select
            value={joinKey ?? ''}
            onChange={(e) => onJoinKeyChange?.(e.target.value || null)}
            className='text-sm border rounded px-2 py-1 text-slate-800 focus:outline-none focus:ring-1 focus:ring-slate-300'
          >
            <option value=''>— select key column —</option>
            {plan.column_profiles.map((c) => (
              <option key={c.name} value={c.name}>{c.name}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  )
}
