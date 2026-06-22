"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { useRouter } from "next/navigation";
import { CheckCircle2, FileSpreadsheet, Loader2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { uploadUrl, triggerIngest } from "@/lib/pipelineApi";
import { uploadFilesToStorage } from "@/lib/uploadToStorage";
import { usePipelineStore } from "@/store/pipelineStore";

// ─── Types ────────────────────────────────────────────────────────────────────

const DOMAINS = ["finance", "healthcare", "retail", "marketing", "operations", "other"] as const;

// Backend job response has two distinct fields: `status` is the job
// lifecycle ("queued" | "running" | "complete" | "error"), while
// `current_step` holds the pipeline/HITL stage ("awaiting_hitl_merge", etc).
// These terminal values live in `current_step`, not `status`.
const TERMINAL_STEPS = [
  "awaiting_hitl_merge",
  "awaiting_hitl_cleaning",
  "awaiting_intent",
  "ready",
];

type FileStatus = "idle" | "uploading" | "done" | "error";

type FileProgress = {
  percent: number   // 0–100
  loaded: number    // bytes sent
  total: number     // file.size
  status: FileStatus
};

type JobPoll = {
  status: string;
  current_step: string | null;
  error?: string;
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

// ─── FileProgressRow ─────────────────────────────────────────────────────────

function FileProgressRow({ file, fp }: { file: File; fp: FileProgress }) {
  const { percent, loaded, total, status } = fp;

  const barColor =
    status === "done"  ? "bg-green-500" :
    status === "error" ? "bg-destructive" :
    "bg-primary";

  const statusIcon =
    status === "done" ? (
      <CheckCircle2 className="w-4 h-4 text-green-500 shrink-0" />
    ) : status === "uploading" ? (
      <Loader2 className="w-4 h-4 text-primary shrink-0 animate-spin" />
    ) : status === "error" ? (
      <AlertCircle className="w-4 h-4 text-destructive shrink-0" />
    ) : null;

  return (
    <li className="border rounded-lg px-4 py-3 space-y-2">
      {/* File name row */}
      <div className="flex items-center gap-2">
        <FileSpreadsheet className="w-4 h-4 text-muted-foreground shrink-0" />
        <span className="flex-1 text-sm font-medium truncate">{file.name}</span>
        {statusIcon}
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-2 rounded-full transition-all duration-300 ease-out ${barColor}`}
          style={{ width: `${percent}%` }}
        />
      </div>

      {/* Stats row */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>
          {status === "done"
            ? "Upload complete"
            : status === "uploading"
            ? `${formatBytes(loaded)} / ${formatBytes(total)}`
            : formatBytes(total)}
        </span>
        <span className={status === "done" ? "text-green-600 font-medium" : ""}>
          {percent}%
        </span>
      </div>
    </li>
  );
}

// ─── UploadPage ───────────────────────────────────────────────────────────────

export default function UploadPage() {
  const router = useRouter();
  const { setDataset, setJobId, setStatus: setPipelineStatus, setError: setPipelineError } =
    usePipelineStore();

  const [domain, setDomain]           = useState<string>("finance");
  const [files, setFiles]             = useState<File[]>([]);
  const [fileProgress, setFileProgress] = useState<Record<string, FileProgress>>({});
  const [phase, setPhase]             = useState<string | null>(null);
  const [error, setError]             = useState<string | null>(null);
  const [uploading, setUploading]     = useState(false);
  const pollerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef  = useRef<AbortController | null>(null);

  // Cleanup poller on unmount
  useEffect(() => {
    return () => {
      if (pollerRef.current) clearInterval(pollerRef.current);
    };
  }, []);

  /** Build initial FileProgress entries (all at 0%) when files are dropped. */
  function initProgress(accepted: File[]): Record<string, FileProgress> {
    const map: Record<string, FileProgress> = {};
    accepted.forEach((f) => {
      map[f.name] = { percent: 0, loaded: 0, total: f.size, status: "idle" };
    });
    return map;
  }

  const onDrop = useCallback((accepted: File[], rejected: FileRejection[]) => {
    // Surface rejection reasons clearly
    if (rejected.length > 0) {
      const reasons = rejected.flatMap((r) =>
        r.errors.map((e) => {
          if (e.code === "file-too-large")
            return `"${r.file.name}" exceeds the 50 MB limit`;
          if (e.code === "too-many-files")
            return `Max 10 files allowed per upload`;
          if (e.code === "file-invalid-type")
            return `"${r.file.name}" is not a supported format (CSV, XLSX, JSON, Parquet)`;
          return `"${r.file.name}": ${e.message}`;
        })
      );
      // Deduplicate identical messages (e.g. multiple "too-many-files")
      setError(Array.from(new Set(reasons)).join(" · "));
      return;
    }
    const capped = accepted.slice(0, 10);
    setFiles(capped);
    setFileProgress(initProgress(capped));
    setError(null);
    setPhase(null);
  }, []);

  // Expose a window hook so Playwright tests can inject files directly into
  // component state without fighting DataTransfer/async-clearing issues.
  useEffect(() => {
    (window as any).__datamind_testDrop = (
      fileDefs: Array<{ name: string; content: string; type?: string }>,
      reject?: Array<{ name: string; code: string }>
    ) => {
      const accepted = fileDefs.map((d) =>
        new File([d.content], d.name, { type: d.type ?? 'text/csv' })
      );
      const rejected = (reject ?? []).map((r) => ({
        file: new File([], r.name),
        errors: [{ code: r.code, message: r.code }],
      }));
      onDrop(accepted, rejected as any);
    };
    return () => {
      delete (window as any).__datamind_testDrop;
    };
  }, [onDrop]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "text/csv": [".csv"],
      "application/json": [".json"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xlsx"],
      "application/octet-stream": [".parquet"],
    },
    maxFiles: 10,
    maxSize: 50 * 1024 * 1024,
  });

  /** Mark one file's status in the progress map. */
  function setFileStatus(name: string, status: FileStatus) {
    setFileProgress((prev) => ({
      ...prev,
      [name]: { ...prev[name], status },
    }));
  }

  async function handleUpload() {
    if (!files.length || uploading) return;
    setUploading(true);
    setError(null);

    try {
      // 0. Persist domain (best-effort)
      api.patch("/datasets/me/domain", { domain }).catch(() => {});

      // 1. Request presigned upload URLs
      setPhase("Requesting upload URLs…");
      const { data } = await uploadUrl(files.map((f) => f.name));
      const { dataset_id, upload_urls } = data;

      // Mark all files as "uploading"
      setFileProgress((prev) => {
        const next = { ...prev };
        files.forEach((f) => { next[f.name] = { ...next[f.name], status: "uploading" }; });
        return next;
      });

      // 2. PUT files directly to Supabase Storage via presigned URLs
      setPhase("Uploading files…");
      abortRef.current = new AbortController();

      await uploadFilesToStorage(
        files.map((file) => {
          const url = upload_urls[file.name];
          if (!url) throw new Error(`No presigned URL for "${file.name}"`);
          return { url, file };
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
                status: percent === 100 ? "done" : "uploading",
              },
            }));
          },
        }
      );

      // Ensure all bars show 100% done
      setFileProgress((prev) => {
        const next = { ...prev };
        files.forEach((f) => {
          next[f.name] = { ...next[f.name], percent: 100, status: "done" };
        });
        return next;
      });

      // 3. Trigger ingestion pipeline
      setPhase("Starting ingestion pipeline…");
      const { data: ingestData } = await triggerIngest(dataset_id);
      const job_id = ingestData.job_id;

      setDataset(dataset_id);
      setJobId(job_id);
      setPipelineStatus("profiling");

      // 4. Poll job status
      setPhase(`Pipeline running · job ${job_id}`);
      let attempts = 0;
      pollerRef.current = setInterval(async () => {
        attempts++;
        try {
          const { data: job } = await api.get<JobPoll>(`/jobs/${job_id}`);
          setPhase(
            `Pipeline: ${job.status}${job.current_step ? ` · ${job.current_step}` : ""}`
          );
          setPipelineStatus(job.status as any);

          const jobFailed = job.status === "error";
          const stepIsTerminal = job.current_step !== null && TERMINAL_STEPS.includes(job.current_step);

          if (jobFailed || stepIsTerminal || attempts > 90) {
            clearInterval(pollerRef.current!);
            pollerRef.current = null;
            setUploading(false);

            if (job.current_step === "awaiting_hitl_merge") {
              window.location.href = `/validate/${dataset_id}`;
            } else if (jobFailed) {
              const msg = job.error ?? "Pipeline failed.";
              setError(msg);
              setPipelineError(msg);
            }
          }
        } catch {
          // transient poll failure — keep retrying
        }
      }, 3000);
    } catch (e: unknown) {
      // Mark any still-uploading files as error
      setFileProgress((prev) => {
        const next = { ...prev };
        files.forEach((f) => {
          if (next[f.name]?.status === "uploading") {
            next[f.name] = { ...next[f.name], status: "error" };
          }
        });
        return next;
      });
      const msg = e instanceof Error ? e.message : "Upload failed.";
      setError(msg);
      setPipelineError(msg);
      setUploading(false);
    }
  }

  // Derived: overall progress across all files
  const totalBytes    = files.reduce((s, f) => s + f.size, 0);
  const uploadedBytes = files.reduce((s, f) => s + (fileProgress[f.name]?.loaded ?? 0), 0);
  const overallPct    = totalBytes > 0 ? Math.round((uploadedBytes / totalBytes) * 100) : 0;
  const allDone       = files.length > 0 && files.every((f) => fileProgress[f.name]?.status === "done");

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">Upload Data</h1>
        <p className="text-muted-foreground mt-1">
          Upload CSV, XLSX, JSON, or Parquet files. Up to 10 files, 50 MB each.
        </p>
      </div>

      {/* Domain selector */}
      <div className="space-y-2">
        <label className="text-sm font-medium" htmlFor="domain-select">
          Business Domain
        </label>
        <select
          id="domain-select"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          disabled={uploading}
          className="w-full border rounded-md px-3 py-2 text-sm disabled:opacity-50"
        >
          {DOMAINS.map((d) => (
            <option key={d} value={d}>
              {d.charAt(0).toUpperCase() + d.slice(1)}
            </option>
          ))}
        </select>
      </div>

      {/* Dropzone */}
      <div
        data-testid="upload-zone"
        {...getRootProps()}
        className={[
          "border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors",
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-muted-foreground/30 hover:border-primary hover:bg-primary/5",
          uploading ? "pointer-events-none opacity-60" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <input {...getInputProps()} />
        {isDragActive ? (
          <p className="text-sm">Drop files here…</p>
        ) : (
          <p className="text-muted-foreground text-sm">
            Drag &amp; drop files here, or click to browse
          </p>
        )}
      </div>

      {/* Per-file progress rows — visible as soon as files are dropped */}
      {files.length > 0 && (
        <div className="space-y-3">
          {/* Overall progress summary (only visible during or after upload) */}
          {uploading && (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  {allDone
                    ? `All ${files.length} file${files.length > 1 ? "s" : ""} uploaded`
                    : `Uploading ${files.length} file${files.length > 1 ? "s" : ""}…`}
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
                fp={fileProgress[f.name] ?? { percent: 0, loaded: 0, total: f.size, status: "idle" }}
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
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          {uploading && <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />}
          <span>{phase}</span>
        </div>
      )}

      {/* Action button */}
      <button
        onClick={handleUpload}
        disabled={!files.length || uploading}
        className="w-full rounded-md bg-primary py-2.5 text-sm font-medium text-primary-foreground disabled:opacity-50 transition-opacity"
      >
        {uploading ? "Processing…" : "Upload & Analyze"}
      </button>
    </div>
  );
}
