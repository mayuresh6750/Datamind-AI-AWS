import { cn } from '@/lib/utils'

type Props = { score: number; showNumber?: boolean }
export function ConfidenceBadge({ score, showNumber = true }: Props) {
  const pct = Math.round(score * 100)
  const tier =
    pct >= 90
      ? { label: 'High', cls: 'bg-green-50 text-green-700 border-green-200' }
      : pct >= 70
      ? { label: 'Medium', cls: 'bg-amber-50 text-amber-700 border-amber-200' }
      : pct >= 50
      ? { label: 'Low', cls: 'bg-orange-50 text-orange-700 border-orange-200' }
      : { label: 'Very low', cls: 'bg-red-50 text-red-700 border-red-200' }
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border',
        tier.cls
      )}
    >
      <span className='w-1.5 h-1.5 rounded-full bg-current' />
      {tier.label}
      {showNumber && ` ${pct}%`}
    </span>
  )
}
