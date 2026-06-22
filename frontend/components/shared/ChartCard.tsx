"use client"
import {
  BarChart, Bar,
  LineChart, Line,
  XAxis, YAxis, Tooltip, CartesianGrid,
  ResponsiveContainer, Legend,
} from 'recharts'
import type { ChartSpec } from '@/types/pipeline'

// ─── Shared chart wrapper ─────────────────────────────────────────────────────

function ChartShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className='rounded-xl border bg-white shadow-sm p-4 flex flex-col gap-3'>
      <p className='text-sm font-semibold text-slate-700'>{title}</p>
      {children}
    </div>
  )
}

function EmptyState() {
  return (
    <div className='h-[220px] flex items-center justify-center text-xs text-slate-400'>
      No data available
    </div>
  )
}

// ─── TableView ────────────────────────────────────────────────────────────────

function TableView({ title, data }: { title: string; data: Record<string, unknown>[] }) {
  if (data.length === 0) {
    return (
      <div className='rounded-xl border bg-white shadow-sm overflow-hidden'>
        <p className='px-4 py-3 text-sm font-semibold text-slate-700 border-b'>{title}</p>
        <EmptyState />
      </div>
    )
  }

  const keys = Object.keys(data[0])
  const visible = data.slice(0, 50)

  return (
    <div className='rounded-xl border bg-white shadow-sm overflow-hidden'>
      <p className='px-4 py-3 text-sm font-semibold text-slate-700 border-b'>{title}</p>
      <div className='overflow-x-auto'>
        <table className='w-full text-xs'>
          <thead className='bg-slate-50 text-slate-500 uppercase'>
            <tr>
              {keys.map((k) => (
                <th key={k} className='px-4 py-2 text-left font-medium whitespace-nowrap'>
                  {k}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className='divide-y divide-slate-100'>
            {visible.map((row, i) => (
              <tr key={i} className='hover:bg-slate-50 transition-colors'>
                {keys.map((k) => (
                  <td key={k} className='px-4 py-2 text-slate-700 whitespace-nowrap'>
                    {String(row[k] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {data.length > 50 && (
          <p className='px-4 py-2 text-xs text-slate-400 border-t'>
            Showing 50 of {data.length} rows
          </p>
        )}
      </div>
    </div>
  )
}

// ─── BarChartView ─────────────────────────────────────────────────────────────

function BarChartView({ title, data, x_field, y_field, color_field }: {
  title: string
  data: Record<string, unknown>[]
  x_field: string
  y_field: string
  color_field?: string | null
}) {
  if (data.length === 0) {
    return <ChartShell title={title}><EmptyState /></ChartShell>
  }

  const chartData = data.map((row) => ({
    ...row,
    [y_field]: parseFloat(String(row[y_field] ?? 0)) || 0,
  }))

  // Truncate long x-axis labels
  const tickFormatter = (v: string) => v.length > 14 ? v.slice(0, 13) + '…' : v

  return (
    <ChartShell title={title}>
      <ResponsiveContainer width='100%' height={220}>
        <BarChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray='3 3' stroke='#f1f5f9' vertical={false} />
          <XAxis
            dataKey={x_field}
            tick={{ fontSize: 11, fill: '#64748b' }}
            tickFormatter={tickFormatter}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#64748b' }}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }}
            cursor={{ fill: '#f8fafc' }}
          />
          {color_field && <Legend wrapperStyle={{ fontSize: 11 }} />}
          <Bar dataKey={y_field} fill='#3b82f6' radius={[3, 3, 0, 0]} maxBarSize={48} />
        </BarChart>
      </ResponsiveContainer>
    </ChartShell>
  )
}

// ─── LineChartView ────────────────────────────────────────────────────────────

function LineChartView({ title, data, x_field, y_field, color_field }: {
  title: string
  data: Record<string, unknown>[]
  x_field: string
  y_field: string
  color_field?: string | null
}) {
  if (data.length === 0) {
    return <ChartShell title={title}><EmptyState /></ChartShell>
  }

  const chartData = data.map((row) => ({
    ...row,
    [y_field]: parseFloat(String(row[y_field] ?? 0)) || 0,
  }))

  const tickFormatter = (v: string) => v.length > 14 ? v.slice(0, 13) + '…' : v

  return (
    <ChartShell title={title}>
      <ResponsiveContainer width='100%' height={220}>
        <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray='3 3' stroke='#f1f5f9' vertical={false} />
          <XAxis
            dataKey={x_field}
            tick={{ fontSize: 11, fill: '#64748b' }}
            tickFormatter={tickFormatter}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#64748b' }}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e2e8f0' }}
          />
          {color_field && <Legend wrapperStyle={{ fontSize: 11 }} />}
          <Line
            type='monotone'
            dataKey={y_field}
            stroke='#3b82f6'
            strokeWidth={2}
            dot={{ r: 3, fill: '#3b82f6' }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartShell>
  )
}

// ─── Public ChartCard ─────────────────────────────────────────────────────────

export function ChartCard({ chart }: { chart: ChartSpec }) {
  const { chart_type, title, data, x_field, y_field, color_field } = chart

  if (chart_type === 'table') {
    return <TableView title={title} data={data} />
  }
  if (chart_type === 'line') {
    return (
      <LineChartView
        title={title}
        data={data}
        x_field={x_field}
        y_field={y_field}
        color_field={color_field}
      />
    )
  }
  // default: bar
  return (
    <BarChartView
      title={title}
      data={data}
      x_field={x_field}
      y_field={y_field}
      color_field={color_field}
    />
  )
}
