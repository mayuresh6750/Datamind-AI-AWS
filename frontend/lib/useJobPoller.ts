import { useEffect, useRef } from 'react'
import { api } from '@/lib/api'
import { usePipelineStore } from '@/store/pipelineStore'

type JobStatus = {
  status: string
  progress: number
  error?: string
}

export function useJobPoller(jobId: string | null) {
  const setStatus = usePipelineStore.getState().setStatus
  const setError = usePipelineStore.getState().setError
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    if (!jobId) return
    const TERMINAL = ['ready', 'error', 'awaiting_hitl_merge', 'awaiting_hitl_cleaning', 'awaiting_intent']
    timer.current = setInterval(async () => {
      const { data } = await api.get<JobStatus>(`/jobs/${jobId}`)
      setStatus(data.status as any)
      if (TERMINAL.includes(data.status)) {
        clearInterval(timer.current!)
        if (data.status === 'error') setError(data.error ?? 'Unknown error')
      }
    }, 2000)
    return () => clearInterval(timer.current!)
  }, [jobId])
}
