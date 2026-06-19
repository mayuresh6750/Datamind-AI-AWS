"use client";

import type { LlmConfig } from "@/lib/types";

export default function ProviderRow({ config }: { config: LlmConfig }) {
  const overrides = Object.entries(config.per_agent_overrides ?? {});
  const hasOverrides = overrides.length > 0;

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <span className="font-semibold">{config.default_provider}</span>
          <span className="text-muted-foreground mx-1">/</span>
          <span className="text-sm text-muted-foreground">{config.default_model}</span>
        </div>
        <span className="text-xs text-muted-foreground">
          Updated {new Date(config.updated_at).toLocaleDateString()}
        </span>
      </div>

      {hasOverrides && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Per-Agent Overrides
          </p>
          {overrides.map(([agent, override]) => (
            <div key={agent} className="flex items-center gap-2 text-sm">
              <span className="font-medium">{agent}:</span>
              <span className="text-muted-foreground">
                {override.provider} / {override.model}
              </span>
            </div>
          ))}
        </div>
      )}

      {!hasOverrides && (
        <p className="text-xs text-muted-foreground">No per-agent overrides</p>
      )}
    </div>
  );
}
