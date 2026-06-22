"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import type { HealthData } from "@/lib/types";

/* ── helpers ─────────────────────────────────────────────────────────── */

function extractApiError(err: unknown, fallback: string): string {
  if (typeof err === "object" && err !== null && "response" in err) {
    const data = (err as { response?: { data?: { detail?: unknown } } })
      .response?.data;
    if (typeof data?.detail === "string") return data.detail;
    if (typeof data?.detail === "object" && data.detail !== null)
      return JSON.stringify(data.detail);
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

const AUTO_REFRESH_MS = 30_000; // 30 seconds

/* ── component ───────────────────────────────────────────────────────── */

export default function AdminHealthPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const { data } = await api.get<HealthData>("/admin/health");
      setHealth(data);
      setLastUpdated(new Date());
    } catch (err: unknown) {
      setLoadError(extractApiError(err, "Failed to load system health."));
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  // Auto-refresh interval
  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(fetchHealth, AUTO_REFRESH_MS);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh, fetchHealth]);

  /* ── render ──────────────────────────────────────────────────────── */

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1 className="text-2xl font-bold">System Health</h1>

        <div className="flex items-center gap-3">
          {/* Auto-refresh toggle */}
          <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
            <input
              id="auto-refresh-toggle"
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="h-4 w-4 rounded border focus:ring-2 focus:ring-ring"
            />
            Auto-refresh (30s)
          </label>

          {/* Manual refresh */}
          <button
            id="manual-refresh-btn"
            type="button"
            onClick={fetchHealth}
            disabled={loading}
            className="rounded-md border px-3 py-1.5 text-sm font-medium hover:bg-accent transition-colors disabled:opacity-50"
          >
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {/* Last-updated indicator */}
      {lastUpdated && (
        <p className="text-xs text-muted-foreground">
          Last updated:{" "}
          {lastUpdated.toLocaleTimeString(undefined, {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })}
        </p>
      )}

      {/* Error banner */}
      {loadError && (
        <div
          role="alert"
          aria-live="assertive"
          className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {loadError}
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Queued / Running */}
        <div className="rounded-lg border p-5 space-y-1">
          <p className="text-sm text-muted-foreground">
            Queued / Running Jobs
          </p>
          {loading && health === null ? (
            <div className="h-9 w-20 animate-pulse rounded bg-muted" />
          ) : (
            <p className="text-3xl font-bold tabular-nums">
              {health?.queued_jobs ?? "—"}
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            Pipeline runs currently queued or in progress.
          </p>
        </div>

        {/* Failed 24h */}
        <div className="rounded-lg border p-5 space-y-1">
          <p className="text-sm text-muted-foreground">
            Failed Jobs (Last 24h)
          </p>
          {loading && health === null ? (
            <div className="h-9 w-20 animate-pulse rounded bg-muted" />
          ) : (
            <p
              className={`text-3xl font-bold tabular-nums ${
                (health?.failed_24h ?? 0) > 0
                  ? "text-red-600"
                  : "text-green-600"
              }`}
            >
              {health?.failed_24h ?? "—"}
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            Pipeline runs that failed in the last 24 hours.
          </p>
        </div>
      </div>

      {/* Status summary */}
      {health && !loadError && (
        <div className="rounded-lg border bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
          {health.queued_jobs === 0 && health.failed_24h === 0 ? (
            <span className="text-green-700 font-medium">
              ✓ All systems healthy — no queued jobs, no failures in the last 24h.
            </span>
          ) : health.failed_24h > 0 ? (
            <span className="text-amber-700 font-medium">
              ⚠ {health.failed_24h} pipeline{health.failed_24h > 1 ? "s" : ""}{" "}
              failed in the last 24 hours. Check pipeline logs for details.
            </span>
          ) : (
            <span>
              {health.queued_jobs} job{health.queued_jobs > 1 ? "s" : ""}{" "}
              currently in the queue.
            </span>
          )}
        </div>
      )}
    </div>
  );
}
