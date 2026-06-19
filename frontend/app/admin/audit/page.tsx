"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import type { AuditEntry } from "@/lib/types";

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

/** Show shortened UUID: first 8 chars */
function shortId(id: string | null): string {
  if (!id) return "—";
  return id.length > 8 ? id.slice(0, 8) + "…" : id;
}

/** Format ISO timestamp to local, human-readable string */
function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

/* ── constants ───────────────────────────────────────────────────────── */

const LIMIT_OPTIONS = [50, 100, 200, 500, 1000] as const;

/* ── component ───────────────────────────────────────────────────────── */

export default function AdminAuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [agentFilter, setAgentFilter] = useState("");
  const [limit, setLimit] = useState<number>(100);

  // Tracks the last-submitted filter so we only re-fetch on explicit search
  const [submittedAgent, setSubmittedAgent] = useState("");
  const searchInputRef = useRef<HTMLInputElement>(null);

  const fetchAudit = useCallback(
    async (agent: string, fetchLimit: number) => {
      setLoading(true);
      setLoadError(null);
      try {
        const params: Record<string, string | number> = { limit: fetchLimit };
        if (agent.trim()) params.agent_name = agent.trim();
        const { data } = await api.get<AuditEntry[]>("/admin/audit", {
          params,
        });
        setEntries(data);
      } catch (err: unknown) {
        setLoadError(extractApiError(err, "Failed to load audit log."));
        setEntries([]);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // Initial fetch + re-fetch when submitted filters change
  useEffect(() => {
    fetchAudit(submittedAgent, limit);
  }, [submittedAgent, limit, fetchAudit]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    setSubmittedAgent(agentFilter);
  }

  function handleClearFilter() {
    setAgentFilter("");
    setSubmittedAgent("");
    searchInputRef.current?.focus();
  }

  /* ── render ──────────────────────────────────────────────────────── */

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Audit Log</h1>

      {/* ── Controls bar ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-end gap-4">
        <form
          onSubmit={handleSearch}
          className="flex items-end gap-2"
        >
          <div>
            <label
              htmlFor="audit-agent-filter"
              className="block text-xs font-medium text-muted-foreground mb-1"
            >
              Agent Name
            </label>
            <input
              ref={searchInputRef}
              id="audit-agent-filter"
              type="text"
              placeholder="e.g. profiler_agent"
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              className="rounded-md border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring w-56"
            />
          </div>
          <button
            type="submit"
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Search
          </button>
          {submittedAgent && (
            <button
              type="button"
              onClick={handleClearFilter}
              className="rounded-md border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent transition-colors"
            >
              Clear
            </button>
          )}
        </form>

        <div>
          <label
            htmlFor="audit-limit"
            className="block text-xs font-medium text-muted-foreground mb-1"
          >
            Max Results
          </label>
          <select
            id="audit-limit"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="rounded-md border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {LIMIT_OPTIONS.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Error banner ─────────────────────────────────────────── */}
      {loadError && (
        <div
          role="alert"
          aria-live="assertive"
          className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {loadError}
        </div>
      )}

      {/* ── Data table ───────────────────────────────────────────── */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-muted-foreground">
              <th className="text-left py-2 pr-3">Agent</th>
              <th className="text-left py-2 pr-3">Action</th>
              <th className="text-left py-2 pr-3 max-w-xs">Rationale</th>
              <th className="text-right py-2 pr-3">Confidence</th>
              <th className="text-right py-2 pr-3">Rows</th>
              <th className="text-left py-2 pr-3">Dataset</th>
              <th className="text-left py-2 pr-3">Run</th>
              <th className="text-left py-2">Created</th>
            </tr>
          </thead>
          <tbody>
            {/* Loading skeleton */}
            {loading &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`skel-${i}`} className="border-b animate-pulse">
                  <td colSpan={8} className="py-3">
                    <div className="h-4 rounded bg-muted w-full" />
                  </td>
                </tr>
              ))}

            {/* Data rows */}
            {!loading &&
              entries.map((e) => (
                <tr
                  key={e.entry_id}
                  className="border-b hover:bg-accent/50 transition-colors"
                >
                  <td className="py-2 pr-3 font-medium whitespace-nowrap">
                    {e.agent_name}
                  </td>
                  <td className="py-2 pr-3 whitespace-nowrap">
                    <span className="inline-block rounded-full bg-muted px-2 py-0.5 text-xs">
                      {e.action_type}
                    </span>
                  </td>
                  <td
                    className="py-2 pr-3 max-w-xs truncate"
                    title={e.rationale ?? undefined}
                  >
                    {e.rationale ?? "—"}
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {e.confidence !== null
                      ? `${(e.confidence * 100).toFixed(0)}%`
                      : "—"}
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {e.rows_affected ?? "—"}
                  </td>
                  <td
                    className="py-2 pr-3 font-mono text-xs"
                    title={e.dataset_id ?? undefined}
                  >
                    {shortId(e.dataset_id)}
                  </td>
                  <td
                    className="py-2 pr-3 font-mono text-xs"
                    title={e.run_id ?? undefined}
                  >
                    {shortId(e.run_id)}
                  </td>
                  <td className="py-2 whitespace-nowrap">{fmtDate(e.created_at)}</td>
                </tr>
              ))}

            {/* Empty state */}
            {!loading && !loadError && entries.length === 0 && (
              <tr>
                <td
                  colSpan={8}
                  className="py-8 text-center text-muted-foreground"
                >
                  {submittedAgent
                    ? `No audit logs found for agent "${submittedAgent}".`
                    : "No audit logs found."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Footer count ─────────────────────────────────────────── */}
      {!loading && entries.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Showing {entries.length} {entries.length === 1 ? "entry" : "entries"}
          {submittedAgent ? ` for agent "${submittedAgent}"` : ""}
        </p>
      )}
    </div>
  );
}
