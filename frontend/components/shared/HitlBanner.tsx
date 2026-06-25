import { ShieldCheck } from 'lucide-react'

type Props = {
  checkpoint: string
  detail?: string
}

export function HitlBanner({ checkpoint, detail }: Props) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-400 text-white mt-0.5">
        <ShieldCheck className="h-3.5 w-3.5" />
      </span>
      <div>
        <p className="text-sm font-semibold text-amber-900">
          Human-in-the-loop checkpoint {checkpoint}
        </p>
        <p className="text-xs text-amber-700 mt-0.5">
          {detail && `${detail} · `}The pipeline will not proceed until you review and confirm.
        </p>
      </div>
    </div>
  )
}
