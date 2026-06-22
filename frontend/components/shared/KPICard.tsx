interface KPICardProps {
  label: string
  value: string
  /** Absolute change string, e.g. "+$12k" or "-3 pts". Displayed in parentheses next to change_pct. */
  change?: string | null
  /** Percentage change. Positive → green ▲, negative → red ▼, zero → slate →. */
  change_pct?: number | null
}

export function KPICard({ label, value, change, change_pct }: KPICardProps) {
  const hasChange = change_pct != null

  let arrow: string
  let colorClass: string
  if (!hasChange || change_pct === 0) {
    arrow = '→'
    colorClass = 'text-slate-400'
  } else if (change_pct! > 0) {
    arrow = '▲'
    colorClass = 'text-emerald-600'
  } else {
    arrow = '▼'
    colorClass = 'text-red-500'
  }

  return (
    <div className='rounded-xl border bg-white px-5 py-4 shadow-sm flex flex-col gap-1.5 min-w-[150px]'>
      <p className='text-xs font-medium text-slate-500 uppercase tracking-wide leading-none'>
        {label}
      </p>
      <p className='text-2xl font-bold text-slate-900 leading-tight tabular-nums'>
        {value}
      </p>
      {hasChange && (
        <p className={`text-xs font-semibold flex items-center gap-1 ${colorClass}`}>
          <span>{arrow}</span>
          <span>{Math.abs(change_pct!).toFixed(1)}%</span>
          {change && <span className='font-normal text-slate-400'>({change})</span>}
        </p>
      )}
    </div>
  )
}
