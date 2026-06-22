"use client"
import React from 'react'
import type { ColumnProfile } from '@/types/pipeline'

const CLASSIFICATION_COLOURS: Record<string, string> = {
  numeric: 'bg-blue-50 text-blue-700',
  textual: 'bg-purple-50 text-purple-700',
  ambiguous: 'bg-orange-50 text-orange-700',
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
    <div className='border rounded-lg overflow-hidden'>
      <div className='overflow-x-auto'>
        <table className='w-full text-sm'>
          <thead>
            <tr className='border-b bg-slate-50'>
              <th className='px-3 py-2 w-8' title='Include column'></th>
              <th className='text-left px-3 py-2 font-medium text-slate-600'>Column</th>
              <th className='text-left px-3 py-2 font-medium text-slate-600'>Type</th>
              <th className='text-right px-3 py-2 font-medium text-slate-600'>Nulls</th>
              <th className='text-right px-3 py-2 font-medium text-slate-600'>Distinct</th>
              <th className='text-right px-3 py-2 font-medium text-slate-600'>Avg length</th>
              <th className='text-left px-3 py-2 font-medium text-slate-600'>Classification</th>
            </tr>
          </thead>
          <tbody className='divide-y divide-slate-100'>
            {columns.map((c) => {
              const excluded = excludedColumns.includes(c.name)
              return (
                <tr key={c.name} className={`hover:bg-slate-50 ${excluded ? 'opacity-40' : ''}`}>
                  <td className='px-3 py-2 text-center'>
                    <input
                      type='checkbox'
                      checked={!excluded}
                      onChange={(e) => onExcludeToggle?.(c.name, !e.target.checked)}
                      className='h-4 w-4 rounded border-slate-300 text-blue-600 cursor-pointer'
                      title={excluded ? 'Excluded — click to include' : 'Included — click to exclude'}
                    />
                  </td>
                  <td className='px-3 py-2 font-mono text-xs text-slate-800'>{c.name}</td>
                  <td className='px-3 py-2 text-slate-600'>{c.dtype}</td>
                  <td className='px-3 py-2 text-right text-slate-500'>{c.null_count}</td>
                  <td className='px-3 py-2 text-right text-slate-500'>{c.distinct_count}</td>
                  <td className='px-3 py-2 text-right text-slate-500'>{c.avg_length !== null ? c.avg_length.toFixed(2) : '—'}</td>
                  <td className='px-3 py-2'>
                    <select
                      defaultValue={c.classification}
                      onChange={(e) => onClassificationChange?.(c.name, e.target.value)}
                      disabled={excluded}
                      className={`text-xs px-2 py-1 rounded border-0 font-medium cursor-pointer focus:ring-1 focus:ring-slate-300 ${CLASSIFICATION_COLOURS[c.classification] ?? ''}`}
                    >
                      <option value='numeric'>numeric</option>
                      <option value='textual'>textual</option>
                      <option value='ambiguous'>ambiguous</option>
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
