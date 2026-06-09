"use client"
import { useCallback, useRef, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useRouter } from 'next/navigation'
import { Upload, FileSpreadsheet, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import { uploadUrl, triggerIngest } from '@/lib/pipelineApi'
import { uploadFilesToStorage } from '@/lib/uploadToStorage'
import { usePipelineStore } from '@/store/pipelineStore'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

// ─── Types ────────────────────────────────────────────────────────────────────

const MAX_PER_FILE = 50 * 1024 * 1024  // 50 MB
const MAX_TOTAL    = 250 * 1024 * 1024 // 250 MB
const TERMINAL_STATUSES = [
  'awaiting_hitl_merge',
  'awaiting_hitl_cleaning',
  'awaiting_intent',
  'ready',
  'error',
]

type FileStatus   = 'idle' | 'uploading' | 'done' | 'error'
type FileProgress = { percent: number; loaded: number; total: number; status: FileStatus }
type JobPoll      = { status: string; current_step: string | null; error?: string }

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

// ─── FileProgressRow ─────────────────────────────────────────────────────────

function FileProgressRow({ file, fp }: { file: File; fp: FileProgress }) {
  const { percent, loaded, total, status } = fp

  const barColor =
    status === 'done'  ? 'bg-green-500' :
    status === 'error' ? 'bg-destructive' :
    'bg-primary'

  const statusIcon =
    status === 'done' ? (
      <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
    ) : status === 'uploading' ? (
      <Loader2 className="w-4 h-4 text-primary shrink-0 animate-spin" />
    ) : status === 'error' ? (
      <AlertCircle className="w-4 h-4 text-destructive shrink-0" />
    ) : (
      <FileSpreadsheet className="w-4 h-4 text-muted-foreground shrink-0" />
    )

  return (
    <li className="border rounded-lg px-4 py-3 space-y-2">
      <div className="flex items-center gap-2">
        {statusIcon}
        <span className="flex-1 text-sm font-medium truncate">{file.name}</span>
      </div>

      {/* Progress bar — always visible from the moment the file is added */}
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-2 rounded-full transition-all duration-300 ease-out ${barColor}`}
          style={{ width: `${percent}%` }}
        />
      </div>

      {/* Stats row */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {status === 'done'
            ? 'Upload complete'
            : status === 'uploading'
            ? `${formatBytes(loaded)} / ${formatBytes(total)}`
            : formatBytes(total)}
        </span>
        <span className={status === 'done' ? 'text-green-600 font-medium' : ''}>
          {percent}%
        </span>
      </div>
    </li>
  )
}

// ─── UploadZone ───────────────────────────────────────────────────────────────

interface UploadZoneProps {
  onUploaded?: (datasetId: string) => void
}

export function UploadZone({ onUploaded }: UploadZoneProps) {
  const router = useRouter()
  const { setDataset, setJobId, setStatus: setPipelineStatus, setError: setPipelineError } =
    usePipelineStore()

  const [files, setFiles]               = useState<File[]>([])
  const [fileProgress, setFileProgress] = useState<Record<string, FileProgress>>({})
  const [uploading, setUploading]       = useState(false)
  const [phase, setPhase]               = useState('')
  const [error, setError]               = useState('')
  const pollerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const abortRef  = useRef<AbortController | null>(null)

  function initProgress(accepted: File[]): Record<string, FileProgress> {
    const map: Record<string, FileProgress> = {}
    accepted.forEach((f) => {
      map[f.name] = { percent: 0, loaded: 0, total: f.size, status: 'idle' }
    })
    return map
  }

  const onDrop = useCallback((accepted: File[], rejected: any[]) => {
    if (rejected.length > 0) {
      setError('Some files were rejected — check format (CSV, XLSX, JSON, Parquet) and size limits.')
      return
    }
    const exts = new Set(accepted.map((f) => f.name.split('.').pop()?.toLowerCase()))
    if (exts.size > 1) {
      setError('All files in one upload must share the same format.')
      return
    }
    const total = accepted.reduce((s, f) => s + f.size, 0)
    if (total > MAX_TOTAL) {
      setError('Total upload size exceeds 250 MB.')
      return
    }
    setError('')
    setPhase('')
    setFiles(accepted)
    setFileProgress(initProgress(accepted))
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    maxFiles: 10,
    maxSize: MAX_PER_FILE,
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.ms-excel': ['.xlsx'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/json': ['.json'],
      'application/octet-stream': ['.parquet'],
    },
  })

  const handleUpload = async () => {
    if (!files.length || uploading) return
    setUploading(true)
    setError('')

    try {
      // Step 1 — get presigned URLs
      setPhase('Requesting upload URLs…')
      const { data } = await uploadUrl(files.map((f) => f.name))
      const { dataset_id, upload_urls } = data

      // Mark all as uploading
      setFileProgress((prev) => {
        const next = { ...prev }
        files.forEach((f) => { next[f.name] = { ...next[f.name], status: 'uploading' } })
        return next
      })

      // Step 2 — PUT files to Supabase Storage
      setPhase('Uploading files…')
      abortRef.current = new AbortController()
      await uploadFilesToStorage(
        files.map((file) => {
          const url = upload_urls[file.name]
          if (!url) throw new Error(`No presigned URL for "${file.name}"`)
          return { url, file }
        }),
        {
          signal: abortRef.current.signal,
          onProgress: (filename, { percent, loaded, total }) => {
            setFileProgress((prev) => ({
              ...prev,
              [filename]: {
                percent,
                loaded,
                total,
                status: percent === 100 ? 'done' : 'uploading',
              },
            }))
          },
        }
      )

      // Ensure all bars show 100%
      setFileProgress((prev) => {
        const next = { ...prev }
        files.forEach((f) => {
          next[f.name] = { ...next[f.name], percent: 100, status: 'done' }
        })
        return next
      })

      // Step 3 — trigger ingest
      setPhase('Starting ingestion pipeline…')
      const { data: ingestData } = await triggerIngest(dataset_id)
      const job_id = ingestData.job_id

      setDataset(dataset_id)
      setJobId(job_id)
      setPipelineStatus('profiling')
      onUploaded?.(dataset_id)

      setPhase('Pipeline running…')

      // Step 4 — poll job status
      let attempts = 0
      pollerRef.current = setInterval(async () => {
        attempts++
        try {
          const { data: job } = await api.get<JobPoll>(`/jobs/${job_id}`)
          setPhase(`Pipeline: ${job.status}${job.current_step ? ` · ${job.current_step}` : ''}`)
          setPipelineStatus(job.status as any)

          if (TERMINAL_STATUSES.includes(job.status) || attempts > 90) {
            clearInterval(pollerRef.current!)
            pollerRef.current = null
            setUploading(false)

            if (job.status === 'awaiting_hitl_merge') {
              router.push(`/validate/${dataset_id}`)
            } else if (job.status === 'error') {
              const msg = job.error ?? 'Pipeline failed.'
              setError(msg)
              setPipelineError(msg)
            }
          }
        } catch {
          // transient poll error — keep retrying
        }
      }, 3000)
    } catch (e: unknown) {
      // Mark in-flight files as error
      setFileProgress((prev) => {
        const next = { ...prev }
        files.forEach((f) => {
          if (next[f.name]?.status === 'uploading') {
            next[f.name] = { ...next[f.name], status: 'error' }
          }
        })
        return next
      })
      const msg = e instanceof Error ? e.message : 'Upload failed.'
      setError(msg)
      setPipelineError(msg)
      setUploading(false)
    }
  }

  // Derived overall progress
  const totalBytes    = files.reduce((s, f) => s + f.size, 0)
  const uploadedBytes = files.reduce((s, f) => s + (fileProgress[f.name]?.loaded ?? 0), 0)
  const overallPct    = totalBytes > 0 ? Math.round((uploadedBytes / totalBytes) * 100) : 0
  const allDone       = files.length > 0 && files.every((f) => fileProgress[f.name]?.status === 'done')

  return (
    <div className="space-y-4">
      {/* Dropzone */}
      <div
        {...getRootProps()}
        className={cn(
          'border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors',
          'hover:border-primary hover:bg-primary/5',
          isDragActive && 'border-primary bg-primary/5',
          uploading && 'pointer-events-none opacity-60'
        )}
      >
        <input {...getInputProps()} />
        <Upload className="w-8 h-8 mx-auto mb-3 text-muted-foreground" />
        <p className="text-sm font-medium">Drop files here or click to browse</p>
        <p className="text-xs text-muted-foreground mt-1">
          CSV · XLSX · JSON · Parquet — up to 10 files, 50 MB each
        </p>
      </div>

      {/* File progress rows — shown immediately when files are added */}
      {files.length > 0 && (
        <div className="space-y-3">
          {/* Overall progress bar (visible once upload starts) */}
          {uploading && (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  {allDone
                    ? `All ${files.length} file${files.length > 1 ? 's' : ''} uploaded`
                    : `Uploading ${files.length} file${files.length > 1 ? 's' : ''}…`}
                </span>
                <span className="font-medium">{overallPct}%</span>
              </div>
              <div className="h-1 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-1 bg-primary rounded-full transition-all duration-300"
                  style={{ width: `${overallPct}%` }}
                />
              </div>
            </div>
          )}

          {/* Individual file rows */}
          <ul className="space-y-2">
            {files.map((f) => (
              <FileProgressRow
                key={f.name}
                file={f}
                fp={fileProgress[f.name] ?? { percent: 0, loaded: 0, total: f.size, status: 'idle' }}
              />
            ))}
          </ul>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="flex items-start gap-2 text-sm text-destructive">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Phase status */}
      {phase && !error && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {uploading && <Loader2 className="w-3 h-3 animate-spin shrink-0" />}
          <span>{phase}</span>
        </div>
      )}

      {/* CTA */}
      {files.length > 0 && (
        <button
          onClick={handleUpload}
          disabled={uploading}
          className="w-full rounded-md bg-primary py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-50 transition-opacity"
        >
          {uploading ? 'Uploading…' : 'Upload & Start Pipeline'}
        </button>
      )}
    </div>
  )
}
