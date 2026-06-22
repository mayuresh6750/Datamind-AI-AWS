"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { UsageRow } from "@/lib/types";

function extractApiError(err: unknown, fallback: string): string {
  if (
    typeof err === "object" &&
    err !== null &&
    "response" in err
  ) {
    const detail = (err as { response?: { data?: { detail?: unknown } } })
      .response?.data?.detail;
    if (typeof detail === "string") return detail;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export default function AdminLlmUsagePage() {
  const [usage, setUsage] = useState<UsageRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    api
      .get<UsageRow[]>("/admin/llm-providers/usage")
      .then((r) => setUsage(r.data))
      .catch((err: unknown) =>
        setError(extractApiError(err, "Failed to load LLM usage data."))
      )
      .finally(() => setLoading(false));
  }, []);

  const totalTokens = usage.reduce((s, r) => s + r.total_tokens, 0);
  const totalCost = usage.reduce((s, r) => s + r.total_cost_usd, 0);
  const totalPipelines = usage.reduce((s, r) => s + r.pipeline_count, 0);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">LLM Usage</h1>

      {loading && <p className="text-muted-foreground">Loading…</p>}

      {error && (
        <div
          role="alert"
          aria-live="assertive"
          className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      {!loading && !error && usage.length === 0 && (
        <p className="text-muted-foreground">No usage data yet.</p>
      )}

      {usage.length > 0 && (
        <>
          <div className="grid grid-cols-3 gap-4">
            <div className="border rounded-lg p-4">
              <p className="text-sm text-muted-foreground">Total Spend</p>
              <p className="text-2xl font-bold mt-1">${totalCost.toFixed(4)}</p>
            </div>
            <div className="border rounded-lg p-4">
              <p className="text-sm text-muted-foreground">Total Tokens</p>
              <p className="text-2xl font-bold mt-1">{totalTokens.toLocaleString()}</p>
            </div>
            <div className="border rounded-lg p-4">
              <p className="text-sm text-muted-foreground">Total Pipelines</p>
              <p className="text-2xl font-bold mt-1">{totalPipelines}</p>
            </div>
          </div>

          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="text-left py-2">Provider</th>
                <th className="text-right py-2">Pipelines</th>
                <th className="text-right py-2">Tokens</th>
                <th className="text-right py-2">Cost (USD)</th>
              </tr>
            </thead>
            <tbody>
              {usage.map((row) => (
                <tr key={row.provider} className="border-b">
                  <td className="py-2">{row.provider}</td>
                  <td className="text-right py-2">{row.pipeline_count}</td>
                  <td className="text-right py-2">{row.total_tokens.toLocaleString()}</td>
                  <td className="text-right py-2">${row.total_cost_usd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
