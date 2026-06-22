"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { LlmConfig } from "@/lib/types";
import ProviderRow from "@/components/admin/ProviderRow";

export default function AdminLlmPage() {
  const [configs, setConfigs] = useState<LlmConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    api
      .get<LlmConfig[]>("/admin/llm-providers")
      .then((r) => setConfigs(r.data))
      .catch((err: unknown) => {
        const detail =
          typeof err === "object" &&
          err !== null &&
          "response" in err &&
          typeof (err as { response?: { data?: { detail?: unknown } } }).response?.data
            ?.detail === "string"
            ? (err as { response: { data: { detail: string } } }).response.data.detail
            : "Failed to load LLM provider configuration.";
        setError(detail);
      })
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">LLM Providers</h1>

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

      {!loading && !error && configs.length === 0 && (
        <p className="text-muted-foreground">No LLM providers configured.</p>
      )}

      <div className="space-y-4">
        {configs.map((cfg) => (
          <ProviderRow key={cfg.config_id} config={cfg} />
        ))}
      </div>
    </div>
  );
}
