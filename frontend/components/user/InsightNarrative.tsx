import { Lightbulb } from 'lucide-react'

type Props = { narrative: string; action?: string }
export function InsightNarrative({ narrative, action }: Props) {
  return (
    <div className='border-l-4 border-brand-blue bg-brand-blue-lt rounded-r-lg p-4 mt-4'>
      <div className='flex items-center gap-2 mb-2'>
        <Lightbulb className='w-4 h-4 text-brand-blue' />
        <span className='text-sm font-semibold text-brand-blue'>AI insight</span>
      </div>
      <p className='text-sm text-slate-700 leading-relaxed'>{narrative}</p>
      {action && (
        <p className='text-sm font-medium text-slate-800 mt-2'>
          Suggested action: {action}
        </p>
      )}
    </div>
  )
}
