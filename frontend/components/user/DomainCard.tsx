import * as Icons from 'lucide-react'
import { cn } from '@/lib/utils'

type Domain = { id: string; label: string; icon: string; kpis: string }
type Props = { domain: Domain; selected: boolean; onSelect: () => void }

export function DomainCard({ domain, selected, onSelect }: Props) {
  const Icon = (Icons as any)[domain.icon]
  return (
    <button
      onClick={onSelect}
      className={cn(
        'flex flex-col items-center gap-2 p-4 rounded-xl border text-center transition-all hover:border-brand-blue hover:bg-brand-blue-lt',
        selected && 'border-brand-blue bg-brand-blue-lt border-2'
      )}
    >
      <Icon className={cn('w-6 h-6', selected ? 'text-brand-blue' : 'text-slate-400')} />
      <span className='text-sm font-medium'>{domain.label}</span>
      <span className='text-xs text-slate-400'>{domain.kpis}</span>
    </button>
  )
}
