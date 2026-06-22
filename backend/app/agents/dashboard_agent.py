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

        try:
            dashboard = await self.llm.structured_completion(prompt, DashboardSpec, agent_name="dashboard")
        except Exception as exc:
            log.warning("dashboard_llm_failed", error=str(exc))
            dashboard = self._heuristic_dashboard(spec, numeric_results, textual_results)

        log.info("dashboard_generated", domain=domain, kpi_count=len(dashboard.kpi_cards), chart_count=len(dashboard.charts))
        return dashboard

    def _heuristic_dashboard(
        self,
        spec: AnalysisSpec,
        numeric_results: list[dict],
        textual_results: list[dict],
    ) -> DashboardSpec:
        from app.models.schemas import ChartSpec, KPICard

        kpi_cards: list[KPICard] = []
        for measure in spec.measures[:3]:
            vals = [r.get(measure) for r in numeric_results if r.get(measure) is not None]
            if vals:
                try:
                    avg = sum(float(v) for v in vals) / len(vals)
                    kpi_cards.append(KPICard(label=f"Avg {measure}", value=f"{avg:.2f}"))
                except (ValueError, TypeError):
                    pass
        if not kpi_cards:
            kpi_cards.append(KPICard(label="Total Records", value=str(len(numeric_results) or len(textual_results))))

        charts: list[ChartSpec] = []
        if numeric_results and spec.dimensions and spec.measures:
            dim, measure = spec.dimensions[0], spec.measures[0]
            chart_data = [{"x": str(r.get(dim, "")), "y": r.get(measure, 0)} for r in numeric_results[:20]]
            charts.append(ChartSpec(chart_type="bar", title=f"{measure} by {dim}", data=chart_data, x_field="x", y_field="y"))
        if not charts:
            data = numeric_results[:20] or [{"key": r.get("content", "")[:60], "value": r.get("similarity", 0)} for r in textual_results[:20]]
            first_key = list(data[0].keys())[0] if data else "key"
            last_key = list(data[0].keys())[-1] if data else "value"
            charts.append(ChartSpec(chart_type="table", title="Data Overview", data=data, x_field=first_key, y_field=last_key))

        return DashboardSpec(
            kpi_cards=kpi_cards,
            charts=charts,
            narrative=f"Analysis of '{spec.restatement}' returned {len(numeric_results)} records.",
            recommended_action="Refine your question or explore the charts for deeper insights.",
        )
