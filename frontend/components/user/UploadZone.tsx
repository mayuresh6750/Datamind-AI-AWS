"use client"
import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, FileSpreadsheet, CheckCircle2 } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

const ALLOWED = ['.csv', '.xlsx', '.json', '.parquet']
const MAX_PER_FILE = 50 * 1024 * 1024 // 50 MB
const MAX_TOTAL = 250 * 1024 * 1024 // 250 MB

export function UploadZone({ onUploaded }: { onUploaded: (id: string) => void }) {
  const [files, setFiles] = useState<File[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const onDrop = useCallback((accepted: File[], rejected: any[]) => {
    if (rejected.length > 0) {
      setError('Some files were rejected. Check format and size limits.')
      return
    }
    const exts = new Set(accepted.map((f) => f.name.split('.').pop()))
    if (exts.size > 1) {
      setError('All files in one upload must be the same format.')
      return
    }
    const total = accepted.reduce((s, f) => s + f.size, 0)
    if (total > MAX_TOTAL) {
      setError('Total upload exceeds 250 MB.')
      return
    }
    setError('')
    setFiles(accepted)
  }, [])
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    maxFiles: 10,
    maxSize: MAX_PER_FILE,
    accept: {
      'text/csv': ['.csv'],
      'application/vnd.ms-excel': ['.xlsx'],
      'application/json': ['.json'],
      'application/octet-stream': ['.parquet'],
    },
  })
  const handleUpload = async () => {
    setUploading(true)
    const { data } = await api.post('/datasets/upload-url', {
      filenames: files.map((f) => f.name),
      formats: files.map((f) => f.name.split('.').pop()),
    })
    await Promise.all(
      files.map((file, i) =>
        fetch(data.urls[i], {
          method: 'PUT',
          body: file,
          headers: { 'Content-Type': file.type || 'application/octet-stream' },
        })
      )
    )
    await api.post(`/datasets/${data.dataset_id}/ingest`)
    setUploading(false)
    onUploaded(data.dataset_id)
  }
  return (
    <div>
      <div
        {...getRootProps()}
        className={cn(
          'border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors hover:border-brand-blue hover:bg-brand-blue-lt',
          isDragActive && 'border-brand-blue bg-brand-blue-lt'
        )}
      >
        <input {...getInputProps()} />
        <Upload className='w-8 h-8 mx-auto mb-3 text-slate-400' />
        <p className='text-sm font-medium'>Drop files here or click to browse</p>
        <p className='text-xs text-slate-400 mt-1'>CSV · XLSX · JSON · Parquet — up to 10 files, 50 MB each</p>
      </div>
      {files.length > 0 && (
        <ul className='mt-3 space-y-2'>
          {files.map((f) => (
            <li key={f.name} className='flex items-center gap-2 text-sm border rounded-md px-3 py-2'>
              <FileSpreadsheet className='w-4 h-4 text-brand-blue' />
              <span className='flex-1 font-medium'>{f.name}</span>
              <span className='text-xs text-slate-400'>{(f.size / 1024 / 1024).toFixed(1)} MB</span>
              <CheckCircle2 className='w-4 h-4 text-green-500' />
            </li>
          ))}
        </ul>
      )}
      {error && <p className='text-sm text-red-600 mt-2'>{error}</p>}
      {files.length > 0 && (
        <button
          onClick={handleUpload}
          disabled={uploading}
          className='mt-4 px-4 py-2 bg-brand-blue text-white rounded-md text-sm font-medium disabled:opacity-50'
        >
          {uploading ? 'Uploading…' : 'Continue to validation'}
        </button>
      )}
    </div>
  )
}
