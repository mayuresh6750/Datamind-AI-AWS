import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'

type Props = {
  label: string
  value: string
  delta?: string
  trend?: 'up' | 'down' | 'flat'
}
export function KpiCard({ label, value, delta, trend }: Props) {
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus
  const trendColor = trend === 'up' ? 'text-green-600' : trend === 'down' ? 'text-red-600' : 'text-slate-400'
  return (
    <div className='bg-white border border-slate-200 rounded-xl p-4'>
      <p className='text-xs font-medium text-slate-400 uppercase tracking-wide'>{label}</p>
      <p className='text-2xl font-semibold mt-1'>{value}</p>
      {delta && (
        <p className={cn('flex items-center gap-1 text-xs mt-1', trendColor)}>
          <TrendIcon className='w-3 h-3' />
          {delta}
        </p>
      )}
    </div>
  )
}
