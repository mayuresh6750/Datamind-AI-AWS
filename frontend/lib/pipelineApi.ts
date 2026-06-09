import { api } from './api'
import type { UploadURLResponse, IngestResponse, MergePlanDecision, CleaningDecision, IntentRequest } from '@/types/api'
import type { DashboardSpec } from '@/types/pipeline'

export const uploadUrl = (filenames: string[]) =>
  api.post<UploadURLResponse>('/datasets/upload-url', { filenames })

export const triggerIngest = (datasetId: string) =>
  api.post<IngestResponse>(`/datasets/${datasetId}/ingest`)
export const getMergePlan = (datasetId: string) => api.get(`/datasets/${datasetId}/merge-plan`)
export const confirmMerge = (datasetId: string, d: MergePlanDecision) => api.post(`/datasets/${datasetId}/merge-plan/decision`, d)
export const getCleaningPlan = (datasetId: string) => api.get(`/datasets/${datasetId}/cleaning-plan`)
export const submitCleaningDecisions = (datasetId: string, decisions: CleaningDecision[]) => api.post(`/datasets/${datasetId}/cleaning-plan/decision`, { decisions })
export const submitIntent = (datasetId: string, req: IntentRequest) => api.post(`/datasets/${datasetId}/intent`, req)
export const generateDashboard = (datasetId: string) => api.post('/dashboards/generate', { dataset_id: datasetId })
export const getDashboard = (dashboardId: string): Promise<DashboardSpec> => api.get(`/dashboards/${dashboardId}`).then(r => r.data)
export const pollJob = (jobId: string) => api.get(`/jobs/${jobId}`).then(r => r.data)
export const downloadAuditLog = (jobId: string) => api.get(`/jobs/${jobId}/audit`, { responseType: 'blob' })
