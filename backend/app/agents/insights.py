"""Insights Agent — domain-flavoured narrative and recommended next action."""
import structlog

from app.core.llm import LLMClient
from app.models.schemas import DashboardSpec

log = structlog.get_logger()

_INSIGHTS_PROMPT = """
You are a business insights analyst specialising in {domain}.

Dashboard data:
{dashboard}

Write a 2–3 sentence executive narrative that:
1. Cites at least two specific numbers from the KPI cards or chart data
2. Uses {domain}-appropriate business language
3. Identifies the most important trend or finding

Then provide one concrete recommended_action the business should take.

Return ONLY valid JSON:
{{"narrative": "<your narrative>", "recommended_action": "<one action>"}}
""".strip()


class InsightsAgent:
    """Enriches a dashboard with domain-flavoured narrative and a recommended action."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def enrich(self, dashboard: DashboardSpec, domain: str) -> DashboardSpec:
        from pydantic import BaseModel

        class InsightsOutput(BaseModel):
            narrative: str
            recommended_action: str

        prompt = _INSIGHTS_PROMPT.format(
            domain=domain,
            dashboard=dashboard.model_dump_json(indent=2),
        )

        output = await self.llm.structured_completion(prompt, InsightsOutput, agent_name="insights")

        enriched = dashboard.model_copy(update={
            "narrative": output.narrative,
            "recommended_action": output.recommended_action,
        })
        log.info("insights_generated", domain=domain)
        return enriched
