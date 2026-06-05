"use client"
import React from 'react'
import type { FileSchema, ColumnSchema } from '@/types/pipeline'

export function SchemaTable({
  file,
  onRouteChange,
}: {
  file: FileSchema
  onRouteChange?: (col: string, route: string) => void
}) {
  return (
    <div className='border rounded p-3'>
      <div className='text-sm font-medium mb-2'>{file.filename}</div>
      <table className='w-full text-sm'>
        <thead>
          <tr>
            <th className='text-left'>Name</th>
            <th className='text-left'>Type</th>
            <th className='text-left'>Routing</th>
          </tr>
        </thead>
        <tbody>
          {file.columns.map((c: ColumnSchema) => (
            <tr key={c.name}>
              <td>{c.name}</td>
              <td>{c.inferred_type}</td>
              <td>
                <select
                  defaultValue={c.routing}
                  onChange={(e) => onRouteChange && onRouteChange(c.name, e.target.value)}
                >
                  <option value='relational'>relational</option>
                  <option value='vector'>vector</option>
                  <option value='ambiguous'>ambiguous</option>
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
