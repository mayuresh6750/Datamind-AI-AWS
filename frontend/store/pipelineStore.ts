import { create } from 'zustand'
import type { MergePlan, CleaningPlan, DashboardSpec } from '@/types/pipeline'

type PipelineStatus =
  | 'idle'
  | 'uploaded'
  | 'profiling'
  | 'awaiting_hitl_merge'
  | 'awaiting_hitl_cleaning'
  | 'executing'
  | 'awaiting_intent'
  | 'generating'
  | 'ready'
  | 'error'

interface PipelineState {
  datasetId: string | null
  jobId: string | null
  status: PipelineStatus
  mergePlan: MergePlan | null
  cleaningPlan: CleaningPlan | null
  dashboard: DashboardSpec | null
  error: string | null
  setDataset: (id: string) => void
  setStatus: (s: PipelineStatus) => void
  setMergePlan: (p: MergePlan) => void
  setCleaningPlan: (p: CleaningPlan) => void
  setDashboard: (d: DashboardSpec) => void
  setError: (e: string) => void
  reset: () => void
}

const initial = {
  datasetId: null,
  jobId: null,
  status: 'idle' as PipelineStatus,
  mergePlan: null,
  cleaningPlan: null,
  dashboard: null,
  error: null,
}

export const usePipelineStore = create<PipelineState>()((set) => ({
  ...initial,
  setDataset: (id) => set({ datasetId: id, status: 'uploaded' }),
  setStatus: (s) => set({ status: s }),
  setMergePlan: (p) => set({ mergePlan: p }),
  setCleaningPlan: (p) => set({ cleaningPlan: p }),
  setDashboard: (d) => set({ dashboard: d }),
  setError: (e) => set({ error: e, status: 'error' }),
  reset: () => set(initial),
}))
