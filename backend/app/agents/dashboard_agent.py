"""Dashboard Agent — converts analysis results into KPI cards + chart specs."""
import structlog

from app.core.llm import LLMClient
from app.models.schemas import AnalysisSpec, DashboardSpec

log = structlog.get_logger()

_DASHBOARD_PROMPT = """
You are a dashboard designer for a {domain} analytics platform.

Analysis spec:
{spec}

SQL aggregation results (use these for KPI cards and charts — this is the primary data):
{numeric_results}

Semantic context excerpts (use ONLY for narrative — do NOT put similarity scores in charts):
{textual_snippets}

Rules:
- If SQL results are non-empty: build KPI cards and charts from them. Show dimension values and aggregated measures.
- If SQL results are empty: create one KPI card saying "No data matched" and one table chart with a single row explaining that.
- NEVER use similarity scores or vector search content as chart data.
- narrative: 2-3 sentences citing specific numbers from the SQL results.
- recommended_action: one concrete next step.

Generate a dashboard with:
- 2-3 KPI cards (label, value as string, optional change and change_pct)
- 1-2 charts (bar preferred for group-by; table as fallback)
  - Each chart needs: chart_type, title, data (list of dicts), x_field, y_field, optional color_field

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

        prompt = _DASHBOARD_PROMPT.format(
            domain=domain,
            spec=spec.model_dump_json(indent=2),
            numeric_results=json.dumps(numeric_results[:20], indent=2, default=str),
            textual_snippets=json.dumps(
                [r.get("content", "")[:120] for r in textual_results[:3]], indent=2
            ),
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
        if numeric_results:
            first_row = numeric_results[0]
            result_keys = list(first_row.keys())
            # If result has a "count" column, show total transactions
            if "count" in result_keys:
                total = sum(int(r.get("count") or 0) for r in numeric_results)
                kpi_cards.append(KPICard(label="Total Records", value=str(total)))
                kpi_cards.append(KPICard(label="Groups", value=str(len(numeric_results))))
            else:
                # Numeric measure KPIs
                for measure in spec.measures[:2]:
                    # Case-insensitive match against result keys
                    actual_key = next((k for k in result_keys if k.lower() == measure.lower()), None)
                    if actual_key:
                        vals = [r.get(actual_key) for r in numeric_results if r.get(actual_key) is not None]
                        if vals:
                            try:
                                avg = sum(float(v) for v in vals) / len(vals)
                                kpi_cards.append(KPICard(label=f"Avg {actual_key}", value=f"{avg:.2f}"))
                            except (ValueError, TypeError):
                                pass
                if not kpi_cards:
                    kpi_cards.append(KPICard(label="Groups", value=str(len(numeric_results))))
        else:
            kpi_cards.append(KPICard(label="No Data", value="—"))

        charts: list[ChartSpec] = []
        if numeric_results and spec.dimensions:
            # Use actual column names from results (not spec names) to handle case differences
            # and count-mode results where the metric column is "count" not from spec.measures
            first_row = numeric_results[0]
            result_keys = list(first_row.keys())

            # Identify dimension column: first key that holds a non-numeric value
            dim_col = next(
                (k for k in result_keys if not isinstance(first_row.get(k), (int, float))),
                result_keys[0],
            )
            # Identify metric column: first key that holds a numeric value (not dim_col)
            metric_col = next(
                (k for k in result_keys if k != dim_col and isinstance(first_row.get(k), (int, float))),
                next((k for k in result_keys if k != dim_col), result_keys[-1]),
            )
            # Optional second dimension for color grouping (e.g. City + Medication + count)
            color_col = next(
                (k for k in result_keys if k not in (dim_col, metric_col) and not isinstance(first_row.get(k), (int, float))),
                None,
            )

            chart_data = []
            for r in numeric_results[:20]:
                if r.get(dim_col) in (None, ""):
                    continue
                try:
                    y_val = round(float(r.get(metric_col) or 0), 2)
                except (ValueError, TypeError):
                    y_val = 0.0
                entry: dict = {"x": str(r.get(dim_col, "")), "y": y_val}
                if color_col:
                    entry["color"] = str(r.get(color_col, ""))
                chart_data.append(entry)
            if chart_data:
                metric_label = metric_col.capitalize()
                dim_label = dim_col
                title = (
                    f"{metric_label} by {dim_label} & {color_col}"
                    if color_col
                    else f"{metric_label} by {dim_label}"
                )
                charts.append(ChartSpec(
                    chart_type="bar",
                    title=title,
                    data=chart_data,
                    x_field="x",
                    y_field="y",
                    color_field="color" if color_col else None,
                ))
        if not charts and numeric_results:
            # Show numeric rows as a plain table
            data = numeric_results[:20]
            keys = list(data[0].keys())
            charts.append(ChartSpec(
                chart_type="table",
                title="Query Results",
                data=data,
                x_field=keys[0],
                y_field=keys[-1],
            ))
        if not charts:
            # No numeric data at all — show a "no results" card, not similarity scores
            charts.append(ChartSpec(
                chart_type="table",
                title="No Results",
                data=[{"message": "No data matched your query. Try a different question or check that your data has been processed."}],
                x_field="message",
                y_field="message",
            ))

        narrative = (
            f"Analysis of '{spec.restatement}' returned {len(numeric_results)} groups."
            if numeric_results
            else "No numeric results were found for this query. The question may reference columns not available in the structured data store."
        )
        return DashboardSpec(
            kpi_cards=kpi_cards,
            charts=charts,
            narrative=narrative,
            recommended_action="Refine your question or explore the charts for deeper insights.",
        )
