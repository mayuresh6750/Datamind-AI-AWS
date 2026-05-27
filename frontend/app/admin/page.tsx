"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

interface HealthData {
  queued_jobs: number;
  failed_24h: number;
}

interface UsageRow {
  provider: string;
  total_tokens: number;
  total_cost_usd: number;
  pipeline_count: number;
}

export default function AdminOverviewPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [usage, setUsage] = useState<UsageRow[]>([]);

  useEffect(() => {
    api.get<HealthData>("/admin/health").then(setHealth).catch(() => {});
    api.get<UsageRow[]>("/admin/llm-providers/usage").then(setUsage).catch(() => {});
  }, []);

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">System Overview</h1>

      <div className="grid grid-cols-2 gap-4">
        <div className="border rounded-lg p-4">
          <p className="text-sm text-muted-foreground">Queued / Running Jobs</p>
          <p className="text-3xl font-bold mt-1">{health?.queued_jobs ?? "—"}</p>
        </div>
        <div className="border rounded-lg p-4">
          <p className="text-sm text-muted-foreground">Failed Jobs (all time)</p>
          <p className="text-3xl font-bold mt-1">{health?.failed_24h ?? "—"}</p>
        </div>
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-3">LLM Usage by Provider</h2>
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
            {usage.length === 0 && (
              <tr>
                <td colSpan={4} className="py-4 text-center text-muted-foreground">No usage data yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
