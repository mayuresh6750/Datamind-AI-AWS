/**
 * uploadToStorage.ts
 *
 * Handles direct browser -> AWS S3 Storage uploads via presigned PUT URLs.
 * S3 presigned PUT URL format:
 *   PUT https://<bucket>.s3.<region>.amazonaws.com/<key>?AWSAccessKeyId=...&Signature=...
 *   Content-Type: <file MIME type>
 *   Body: raw file bytes
 */

export interface UploadProgress {
  loaded: number   // bytes sent so far
  total: number    // total file size in bytes
  percent: number  // 0–100
}

export interface UploadResult {
  filename: string
  path: string      // storage key returned by Supabase
  etag?: string
}

export interface StorageUploadOptions {
  /** Called on each XHR progress event. */
  onProgress?: (progress: UploadProgress) => void
  /** AbortSignal from an AbortController — triggers abort on the XHR. */
  signal?: AbortSignal
  /** Max retry attempts on transient failures (5xx / network). Default: 3. */
  maxRetries?: number
}

/** Supabase Storage error shape returned in the JSON response body. */
interface SupabaseStorageError {
  error: string
  message: string
  statusCode: string
}

/**
 * Attempt a single PUT upload to a Supabase presigned URL via XHR.
 * Resolves with the Supabase response body on success; rejects with a
 * descriptive Error on failure.
 */
function attemptXhrUpload(
  presignedUrl: string,
  file: File,
  options: StorageUploadOptions
): Promise<string> {
  const { onProgress, signal } = options

  return new Promise<string>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', presignedUrl)

    // Supabase Storage accepts the MIME type via Content-Type.
    // Fallback to octet-stream for formats like .parquet that may lack a
    // registered browser MIME type.
    xhr.setRequestHeader(
      'Content-Type',
      file.type || 'application/octet-stream'
    )

    // Report upload progress to the caller
    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress({
          loaded: e.loaded,
          total: e.total,
          percent: Math.round((e.loaded / e.total) * 100),
        })
      }
    })

    // Resolve or reject based on HTTP status
    xhr.addEventListener('load', async () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.responseText)
      } else {
        // Try to parse a Supabase-specific error message from the body
        let detail = `HTTP ${xhr.status}`
        try {
          const body = JSON.parse(xhr.responseText) as SupabaseStorageError
          detail = body.message ?? body.error ?? detail
        } catch {
          // response body wasn't JSON — use raw text if short enough
          if (xhr.responseText && xhr.responseText.length < 200) {
            detail = xhr.responseText
          }
        }
        reject(new Error(`Storage upload failed for "${file.name}": ${detail}`))
      }
    })

    xhr.addEventListener('error', () => {
      reject(new Error(`Network error uploading "${file.name}" to storage`))
    })

    xhr.addEventListener('timeout', () => {
      reject(new Error(`Upload timed out for "${file.name}"`))
    })

    // Honour AbortSignal: abort the in-flight XHR if signal fires
    if (signal) {
      if (signal.aborted) {
        xhr.abort()
        reject(new DOMException('Upload aborted', 'AbortError'))
        return
      }
      signal.addEventListener('abort', () => {
        xhr.abort()
        reject(new DOMException('Upload aborted', 'AbortError'))
      })
    }

    xhr.send(file)
  })
}

/**
 * Upload a single file to Supabase Storage via its presigned PUT URL.
 *
 * Automatically retries on transient failures (5xx / network errors) with
 * exponential back-off. Client-side errors (4xx) are never retried.
 *
 * @param presignedUrl   Signed upload URL from POST /datasets/upload-url
 * @param file           Browser File object to upload
 * @param options        Progress callback, AbortSignal, retry config
 * @returns              Resolved UploadResult on success
 * @throws               Error with a user-readable message on permanent failure
 */
export async function uploadFileToStorage(
  presignedUrl: string,
  file: File,
  options: StorageUploadOptions = {}
): Promise<UploadResult> {
  const maxRetries = options.maxRetries ?? 3
  let lastError: Error = new Error('Upload failed')

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const responseText = await attemptXhrUpload(presignedUrl, file, options)

      // Parse Supabase response to extract the storage key/path
      let path = ''
      try {
        const body = JSON.parse(responseText) as { Key?: string; path?: string }
        path = body.Key ?? body.path ?? ''
      } catch {
        // Non-JSON response — path unknown but upload succeeded
      }

      return { filename: file.name, path }
    } catch (err: unknown) {
      const e = err instanceof Error ? err : new Error(String(err))

      // AbortError is not retryable — propagate immediately
      if (e.name === 'AbortError') throw e

      // 4xx errors from Supabase are not retryable (e.g. invalid token, policy denial)
      const is4xx = /HTTP 4\d{2}/.test(e.message)
      if (is4xx) throw e

      lastError = e

      // Exponential back-off before next retry (skip delay on last attempt)
      if (attempt < maxRetries) {
        const delayMs = Math.min(500 * 2 ** (attempt - 1), 4000) // 500 ms, 1 s, 2 s …
        await new Promise((res) => setTimeout(res, delayMs))
      }
    }
  }

  throw lastError
}

/**
 * Upload multiple files concurrently to Supabase Storage.
 *
 * @param uploads   Array of { url, file } pairs (url from upload-url endpoint)
 * @param options   Shared options (signal, maxRetries); onProgress receives
 *                  per-file progress keyed by filename
 * @returns         Array of UploadResult in the same order as `uploads`
 */
export async function uploadFilesToStorage(
  uploads: Array<{ url: string; file: File }>,
  options: {
    onProgress?: (filename: string, progress: UploadProgress) => void
    signal?: AbortSignal
    maxRetries?: number
  } = {}
): Promise<UploadResult[]> {
  return Promise.all(
    uploads.map(({ url, file }) =>
      uploadFileToStorage(url, file, {
        onProgress: options.onProgress
          ? (p) => options.onProgress!(file.name, p)
          : undefined,
        signal: options.signal,
        maxRetries: options.maxRetries,
      })
    )
  )
}
