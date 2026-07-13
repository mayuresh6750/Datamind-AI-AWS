"use client"
import React from 'react'
import type { ColumnProfile } from '@/types/pipeline'

const CLASSIFICATION_STYLES: Record<string, string> = {
  numeric:    'bg-blue-50 text-blue-700 border border-blue-200',
  structured: 'bg-emerald-50 text-emerald-700 border border-emerald-200',
  textual:    'bg-violet-50 text-violet-700 border border-violet-200',
  ambiguous:  'bg-orange-50 text-orange-700 border border-orange-200',
}

export function SchemaTable({
  columns,
  excludedColumns = [],
  onClassificationChange,
  onExcludeToggle,
}: {
  columns: ColumnProfile[]
  excludedColumns?: string[]
  onClassificationChange?: (col: string, classification: string) => void
  onExcludeToggle?: (col: string, excluded: boolean) => void
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50">
              <th className="w-10 px-3 py-2.5" title="Include column" />
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Column</th>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Type</th>
              <th className="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Nulls</th>
              <th className="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Distinct</th>
              <th className="px-3 py-2.5 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Avg length</th>
              <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Classification</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {columns.map((c, i) => {
              const excluded = excludedColumns.includes(c.name)
              return (
                <tr
                  key={c.name}
                  className={[
                    'transition-colors',
                    i % 2 === 0 ? 'bg-white' : 'bg-slate-50/50',
                    excluded ? 'opacity-40' : 'hover:bg-blue-50/30',
                  ].join(' ')}
                >
                  <td className="px-3 py-2.5 text-center">
                    <input
                      type="checkbox"
                      checked={!excluded}
                      onChange={(e) => onExcludeToggle?.(c.name, !e.target.checked)}
                      className="h-4 w-4 cursor-pointer rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                      title={excluded ? 'Excluded — click to include' : 'Included — click to exclude'}
                    />
                  </td>
                  <td className="px-3 py-2.5">
                    <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-800">
                      {c.name}
                    </code>
                  </td>
                  <td className="px-3 py-2.5 text-slate-500">{c.dtype}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-slate-500">{c.null_count}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-slate-500">{c.distinct_count}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums text-slate-500">
                    {c.avg_length !== null ? c.avg_length.toFixed(2) : '—'}
                  </td>
                  <td className="px-3 py-2.5">
                    <select
                      value={c.classification}
                      onChange={(e) => onClassificationChange?.(c.name, e.target.value)}
                      disabled={excluded}
                      className={[
                        'cursor-pointer rounded-full border-0 px-2.5 py-1 text-xs font-semibold',
                        'focus:ring-1 focus:ring-slate-300 focus:outline-none',
                        CLASSIFICATION_STYLES[c.classification] ?? 'bg-slate-100 text-slate-700',
                      ].join(' ')}
                    >
                      <option value="numeric">numeric (→ SQL aggregation)</option>
                      <option value="structured">structured (→ SQL grouping)</option>
                      <option value="textual">textual (→ vector search)</option>
                      <option value="ambiguous">ambiguous</option>
                    </select>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
