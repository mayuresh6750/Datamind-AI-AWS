"use client"
import { useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { submitIntent } from '@/lib/pipelineApi'
import { HitlBanner } from '@/components/shared/HitlBanner'
import { JobProgressBar } from '@/components/shared/JobPoller'
import { useAuthStore } from '@/store/authStore'
import { Lightbulb, Sparkles } from 'lucide-react'

const DOMAIN_CHIPS: Record<string, string[]> = {
  finance: [
    'What is my monthly recurring revenue trend?',
    'Show gross margin by product or category',
    'What is the customer churn rate over time?',
    'Which customers have the highest AR aging?',
    'What is the runway based on current burn rate?',
  ],
  healthcare: [
    'What is the average length of stay by diagnosis?',
    'What is the readmission rate for the past quarter?',
    'Which diagnoses have the highest episode counts?',
    'Show patient volume trends over time',
    'What are the top 5 diagnoses by frequency?',
  ],
  retail: [
    'What is the average order value by channel?',
    'Which SKUs have the highest margin?',
    'What is the return rate by product category?',
    'Show inventory turnover by SKU',
    'Which channels drive the most repeat purchases?',
  ],
  marketing: [
    'What is the customer acquisition cost by channel?',
    'Show CTR and CPA trends by campaign',
    'What is the LTV to CAC ratio?',
    'Which campaigns have the best conversion rate?',
    'What is the attribution breakdown by channel?',
  ],
  operations: [
    'What is the average cycle time by process?',
    'Show throughput trends over the past month',
    'Which stages have the highest bottlenecks?',
    'What is the average processing time per unit?',
    'Show efficiency rates by department',
  ],
  other: [
    'What are the main trends in this dataset?',
    'Show me the top categories by count',
    'What is the distribution of values over time?',
    'Give me a summary of the key metrics',
    'Which records have the most missing values?',
  ],
}

export default function IntentPage() {
  const { id } = useParams() as { id: string }
  const searchParams = useSearchParams()
  const jobId = searchParams.get('job')
  const router = useRouter()
  const activeDomain = useAuthStore((s) => s.activeDomain) ?? 'other'

  const [ready, setReady] = useState(!jobId)   // skip polling if no job_id in URL
  const [question, setQuestion] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (!question.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const r = await submitIntent(id, { dataset_id: id, question: question.trim() })
      const intentJobId = r.data?.job_id
      router.push(`/dashboard/${id}${intentJobId ? `?job=${intentJobId}` : ''}`)
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Something went wrong. Please try again.')
      setSubmitting(false)
    }
  }

  const chips = DOMAIN_CHIPS[activeDomain] ?? DOMAIN_CHIPS.other
  const domainLabel = activeDomain.charAt(0).toUpperCase() + activeDomain.slice(1)

  if (!ready) {
    return (
      <div className='max-w-md space-y-4 py-8'>
        <h1 className='text-lg font-semibold text-slate-800'>Preparing your dataset</h1>
        <p className='text-sm text-slate-500'>Cleaning and routing data — this takes a few seconds…</p>
        <JobProgressBar
          jobId={jobId}
          label='Cleaning data'
          onComplete={() => setReady(true)}
          onFailed={(err) => { setError(err); setReady(true) }}
        />
        {error && (
          <p className='text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2'>{error}</p>
        )}
      </div>
    )
  }

  return (
    <div className='max-w-2xl'>
      <h1 className='text-xl font-semibold mb-1'>What do you want to learn from this data?</h1>

      {/* Instruction callout — indigo so it reads as AI guidance, not invisible hint */}
      <div className='instruction-tip'>
        <Lightbulb className='h-4 w-4 shrink-0 text-indigo-500' />
        <span>Ask in plain English — no SQL or formulas needed. The AI will interpret your question and build the analysis automatically.</span>
      </div>

      <HitlBanner checkpoint='#3' detail='Describe your analysis goal' />

      <div className='mt-4'>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit()
          }}
          placeholder='e.g. What is the average order value by channel?'
          rows={3}
          className='w-full rounded-lg border border-slate-200 bg-white/80 px-3 py-2.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-indigo-300 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-100 resize-none transition-colors'
        />
        <p className='text-xs text-indigo-400 mt-1.5 flex items-center gap-1'>
          <span>⌨</span> Press <kbd className='px-1 py-0.5 rounded bg-slate-100 text-slate-500 text-xs font-mono'>Ctrl+Enter</kbd> to submit instantly
        </p>
      </div>

      {/* Domain suggestion chips */}
      <div className='mt-4'>
        <p className='flex items-center gap-1.5 text-xs font-semibold text-indigo-600 uppercase tracking-wide mb-2.5'>
          <Sparkles className='h-3.5 w-3.5' />
          Suggested questions for {domainLabel}
        </p>
        <div className='flex flex-wrap gap-2'>
          {chips.map((chip) => (
            <button
              key={chip}
              onClick={() => setQuestion(chip)}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${
                question === chip
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-slate-600 border-slate-200 hover:border-blue-400 hover:text-blue-600'
              }`}
            >
              {chip}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p className='mt-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2'>
          {error}
        </p>
      )}

      <div className='flex gap-2 mt-6'>
        <button onClick={() => router.back()} className='btn-outline'>
          Back
        </button>
        <button
          onClick={handleSubmit}
          disabled={submitting || !question.trim()}
          className='btn-primary'
        >
          {submitting ? 'Analysing…' : 'Analyse →'}
        </button>
      </div>
    </div>
  )
}
