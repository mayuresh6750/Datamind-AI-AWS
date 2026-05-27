"""Dashboard Agent — converts analysis results into KPI cards + chart specs."""
import structlog

from app.core.llm import LLMClient
from app.models.schemas import AnalysisSpec, DashboardSpec

log = structlog.get_logger()

_DASHBOARD_PROMPT = """
You are a dashboard designer for a {domain} analytics platform.

Analysis spec:
{spec}

Analysis results (first 20 rows):
{results}

Generate a dashboard with:
- 2-3 KPI cards (label, value as string, optional change and change_pct)
- 2 charts (line or bar preferred; table as fallback)
  - Each chart needs: chart_type, title, data (list of dicts), x_field, y_field, optional color_field
- narrative: 2-3 sentence domain-flavoured business summary citing specific numbers
- recommended_action: one concrete next step the user should take

Return ONLY valid JSON matching this schema:
{schema}
""".strip()


class DashboardAgent:
    """Converts numeric/textual analysis results into a structured DashboardSpec."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def generate(
        self,
        spec: AnalysisSpec,
        numeric_results: list[dict],
        textual_results: list[dict],
        domain: str,
    ) -> DashboardSpec:
        import json

        all_results = numeric_results[:20] + [{"text_result": r.get("content", "")} for r in textual_results[:5]]

        prompt = _DASHBOARD_PROMPT.format(
            domain=domain,
            spec=spec.model_dump_json(indent=2),
            results=json.dumps(all_results, indent=2, default=str),
            schema=DashboardSpec.model_json_schema(),
        )

        dashboard = await self.llm.structured_completion(prompt, DashboardSpec, agent_name="dashboard")
        log.info("dashboard_generated", domain=domain, kpi_count=len(dashboard.kpi_cards), chart_count=len(dashboard.charts))
        return dashboard
