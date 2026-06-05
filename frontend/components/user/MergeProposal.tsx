"use client"
import React from 'react'
import type { MergePlan } from '@/types/pipeline'

export function MergeProposal({ plan, onChange }: { plan: MergePlan; onChange?: (p: Partial<MergePlan>) => void }) {
  return (
    <div className='p-3 border rounded'>
      <h3 className='font-semibold mb-2'>Merge proposal</h3>
      <p className='text-sm text-slate-600 mb-2'>{plan.rationale}</p>
      <div className='text-xs text-slate-500'>Strategy: {plan.merge_strategy}</div>
    </div>
  )
}
