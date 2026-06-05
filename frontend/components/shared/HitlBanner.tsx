import { AlertTriangle } from 'lucide-react'

type Props = {
  checkpoint: string
  detail?: string
}

export function HitlBanner({ checkpoint, detail }: Props) {
  return (
    <div className='flex items-center gap-2 px-3 py-2.5 rounded-md bg-amber-50 border border-amber-200 text-amber-800 text-sm mb-4'>
      <AlertTriangle className='w-4 h-4 flex-shrink-0' />
      <span>
        <strong>HITL checkpoint {checkpoint}</strong>
        {detail && ` — ${detail}`}
        {' '}Cleaning will not proceed until you confirm.
      </span>
    </div>
  )
}
