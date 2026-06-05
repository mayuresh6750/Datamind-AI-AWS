import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import type { VegaLiteSpec } from '@/types/pipeline'

type Props = { title: string; spec: VegaLiteSpec; data: any[] }
export function ChartCard({ title, spec, data }: Props) {
  const isBar = spec.mark === 'bar'
  const isLine = spec.mark === 'line'
  return (
    <div className='bg-white border border-slate-200 rounded-xl p-4'>
      <p className='text-sm font-medium mb-3'>{title}</p>
      <ResponsiveContainer width='100%' height={180}>
        {isBar ? (
          <BarChart data={data}>
            <XAxis dataKey={spec.encoding.x.field} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey={spec.encoding.y.field} fill='#4a8fe8' radius={[3, 3, 0, 0]} />
          </BarChart>
        ) : isLine ? (
          <LineChart data={data}>
            <XAxis dataKey={spec.encoding.x.field} tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip />
            <Line dataKey={spec.encoding.y.field} stroke='#1a6fd4' strokeWidth={2} dot={false} />
          </LineChart>
        ) : (
          <div />
        )}
      </ResponsiveContainer>
    </div>
  )
}
