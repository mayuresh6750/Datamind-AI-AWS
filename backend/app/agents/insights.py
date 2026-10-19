"""Insights Agent — domain-flavoured narrative and recommended next action."""
import structlog

from app.core.llm import LLMClient
from app.models.schemas import DashboardSpec

log = structlog.get_logger()

_INSIGHTS_PROMPT = """
You are a business insights analyst specialising in {domain}.

Dashboard data:
{dashboard}
{semantic_context}

Write a 2–3 sentence executive narrative that:
1. Cites at least two specific numbers from the KPI cards or chart data
2. Uses {domain}-appropriate business language
3. Identifies the most important trend or finding
{semantic_instruction}

Then provide one concrete recommended_action the business should take.

Return ONLY valid JSON:
{{"narrative": "<your narrative>", "recommended_action": "<one action>"}}
""".strip()


class InsightsAgent:
    """Enriches a dashboard with domain-flavoured narrative and a recommended action."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def enrich(
        self,
        dashboard: DashboardSpec,
        domain: str,
        semantic_concept: str | None = None,
    ) -> DashboardSpec:
        from pydantic import BaseModel

        class InsightsOutput(BaseModel):
            narrative: str
            recommended_action: str

        semantic_context = (
            f"\nFiltered Concept / Root Cause: This analysis is specifically filtered by the semantic concept: \"{semantic_concept}\"."
            if semantic_concept else ""
        )
        semantic_instruction = (
            f"4. Explicitly connects the quantitative metric with the qualitative root cause / concept ('{semantic_concept}') retrieved from text data."
            if semantic_concept else ""
        )

        prompt = _INSIGHTS_PROMPT.format(
            domain=domain,
            dashboard=dashboard.model_dump_json(indent=2),
            semantic_context=semantic_context,
            semantic_instruction=semantic_instruction,
        )

        try:
            output = await self.llm.structured_completion(prompt, InsightsOutput, agent_name="insights")
            enriched = dashboard.model_copy(update={
                "narrative": output.narrative,
                "recommended_action": output.recommended_action,
            })
        except Exception as exc:
            log.warning("insights_llm_failed", error=str(exc))
            enriched = self._heuristic_insights(dashboard, domain, semantic_concept=semantic_concept)

        log.info("insights_generated", domain=domain, semantic_concept=semantic_concept)
        return enriched

    def _heuristic_insights(
        self,
        dashboard: DashboardSpec,
        domain: str,
        semantic_concept: str | None = None,
    ) -> DashboardSpec:
        kpi_summary = " ".join(f"{k.label} is {k.value}." for k in dashboard.kpi_cards[:2])
        if semantic_concept:
            narrative = f"For this {domain} dataset: Analysis filtered by '{semantic_concept}'. {kpi_summary} Review the charts above for trends and root-cause details."
            recommended_action = f"Investigate underlying factors contributing to '{semantic_concept}' to optimize business outcomes."
        else:
            narrative = f"For this {domain} dataset: {kpi_summary} Review the charts above for trends and distributions."
            recommended_action = "Explore the visualizations and refine your question for more targeted insights."

        return dashboard.model_copy(update={
            "narrative": narrative,
            "recommended_action": recommended_action,
        })
