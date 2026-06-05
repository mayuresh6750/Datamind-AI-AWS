"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { api } from "@/lib/api";

const DOMAINS = ["finance", "healthcare", "retail", "marketing", "operations", "other"] as const;

export default function UploadPage() {
  const [domain, setDomain] = useState<string>("finance");
  const [files, setFiles] = useState<File[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const onDrop = useCallback((accepted: File[]) => {
    setFiles(accepted.slice(0, 10));
    setError(null);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "text/csv": [".csv"], "application/json": [".json"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"] },
    maxFiles: 10,
    maxSize: 50 * 1024 * 1024,
  });

  async function handleUpload() {
    if (!files.length) return;
    setStatus("Requesting upload URLs…");
    setError(null);

    try {
      const { data } = await api.post<{ dataset_id: string; upload_urls: Record<string, string> }>(
        "/datasets/upload-url",
        { filenames: files.map((f) => f.name) }
      );
      const { dataset_id, upload_urls } = data;

      setStatus("Uploading files…");
      await Promise.all(
        files.map((file) =>
          fetch(upload_urls[file.name], { method: "PUT", body: file, headers: { "Content-Type": file.type } })
        )
      );

      setStatus("Triggering ingestion…");
      const { data: ingestData } = await api.post<{ job_id: string }>(`/datasets/${dataset_id}/ingest`, {});
      const job_id = ingestData.job_id
      setStatus(`Pipeline started. Job ID: ${job_id}. Polling for merge plan…`);

      // Poll for status
      let attempts = 0;
      const interval = setInterval(async () => {
        attempts++;
        const { data: jobStatus } = await api.get<{ status: string; current_step: string | null }>(`/jobs/${job_id}`);
        setStatus(`Job status: ${jobStatus.status} — ${jobStatus.current_step ?? ""}`);
        if (jobStatus.status === "complete" || jobStatus.status === "failed" || attempts > 60) {
          clearInterval(interval);
        }
      }, 3000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      setStatus(null);
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Upload Data</h1>
        <p className="text-muted-foreground mt-1">Upload CSV, XLSX, or JSON files. Up to 10 files, 50 MB each.</p>
      </div>

      <div className="space-y-2">
        <label className="text-sm font-medium">Business Domain</label>
        <select
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          className="w-full border rounded-md px-3 py-2 text-sm"
        >
          {DOMAINS.map((d) => (
            <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
          ))}
        </select>
      </div>

      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
          isDragActive ? "border-primary bg-primary/5" : "border-muted-foreground/30 hover:border-primary"
        }`}
      >
        <input {...getInputProps()} />
        {isDragActive ? (
          <p>Drop files here…</p>
        ) : (
          <p className="text-muted-foreground">Drag & drop files here, or click to browse</p>
        )}
        {files.length > 0 && (
          <ul className="mt-4 text-sm text-left space-y-1">
            {files.map((f) => (
              <li key={f.name} className="flex items-center gap-2">
                <span className="font-mono">{f.name}</span>
                <span className="text-muted-foreground">({(f.size / 1024 / 1024).toFixed(1)} MB)</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && <p className="text-destructive text-sm">{error}</p>}
      {status && <p className="text-sm text-muted-foreground">{status}</p>}

      <button
        onClick={handleUpload}
        disabled={!files.length}
        className="w-full rounded-md bg-primary py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
      >
        Upload & Analyze
      </button>
    </div>
  );
}
