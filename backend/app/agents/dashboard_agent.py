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
            numeric_results=json.dumps(numeric_results[:10], indent=2, default=str),
            textual_snippets=json.dumps(
                [r.get("content", "")[:80] for r in textual_results[:2]], indent=2
            ),
            schema=DashboardSpec.model_json_schema(),
        )

        try:
            dashboard = await self.llm.structured_completion(prompt, DashboardSpec, agent_name="dashboard")
        except Exception as exc:
            log.warning("dashboard_llm_failed", error=str(exc))
            dashboard = self._heuristic_dashboard(spec, numeric_results, textual_results)

        # Always rebuild charts from raw SQL rows — LLM-generated chart/table data can
        # mislabel axes (e.g. repeating "Blood Sugar" when grouping by Lab_Test + Test_Date).
        dashboard.charts = self._build_charts_from_results(spec, numeric_results)
        dashboard.kpi_cards = self._build_kpi_cards(spec, numeric_results)

        log.info("dashboard_generated", domain=domain, kpi_count=len(dashboard.kpi_cards), chart_count=len(dashboard.charts))
        return dashboard

    def _build_kpi_cards(self, spec: AnalysisSpec, numeric_results: list[dict]) -> list:
        from app.models.schemas import KPICard

        if not numeric_results:
            return [KPICard(label="No Data", value="—")]

        first_row = numeric_results[0]
        result_keys = list(first_row.keys())
        key_lower = {k.lower(): k for k in result_keys}

        if "count" in key_lower or spec.aggregation == "count":
            count_key = key_lower.get("count", "count")
            if count_key in result_keys:
                total = sum(int(r.get(count_key) or 0) for r in numeric_results)
                return [
                    KPICard(label="Total Records", value=str(total)),
                    KPICard(label="Groups", value=str(len(numeric_results))),
                ]

        measure_keys = {m.lower() for m in spec.measures}
        kpi_cards: list[KPICard] = []
        for key in result_keys:
            if measure_keys and key.lower() not in measure_keys:
                continue
            if not self._is_numeric_value(first_row.get(key)):
                continue
            vals = [r.get(key) for r in numeric_results if r.get(key) is not None]
            if vals:
                try:
                    avg = sum(float(v) for v in vals) / len(vals)
                    kpi_cards.append(KPICard(label=f"Avg {key}", value=f"{avg:.2f}"))
                except (ValueError, TypeError):
                    pass
        return kpi_cards or [KPICard(label="Groups", value=str(len(numeric_results)))]

    @staticmethod
    def _is_numeric_value(val: object) -> bool:
        if isinstance(val, (int, float)):
            return True
        if val is None or val == "":
            return False
        try:
            float(str(val).replace(",", ""))
            return True
        except (ValueError, TypeError):
            return False

    def _resolve_columns(
        self,
        spec: AnalysisSpec,
        result_keys: list[str],
        first_row: dict,
    ) -> tuple[list[str], str | None]:
        """Map AnalysisSpec dimensions/measures onto actual SQL result column names."""
        key_lower = {k.lower(): k for k in result_keys}

        dim_cols: list[str] = []
        for d in spec.dimensions:
            if d in result_keys:
                dim_cols.append(d)
            elif d.lower() in key_lower:
                dim_cols.append(key_lower[d.lower()])

        if not dim_cols:
            dim_cols = [
                k for k in result_keys
                if not self._is_numeric_value(first_row.get(k))
            ]

        # Prefer spec measures; never treat extra non-numeric columns (e.g. Age) as dimensions
        metric_col: str | None = None
        if spec.aggregation == "count" or (not spec.measures and "count" in key_lower):
            metric_col = key_lower.get("count")

        for m in spec.measures:
            if m in result_keys:
                metric_col = m
                break
            if m.lower() in key_lower:
                metric_col = key_lower[m.lower()]
                break

        if not metric_col and spec.measures:
            return dim_cols, None

        if not metric_col:
            measure_keys = {d.lower() for d in spec.dimensions}
            allowed_measures = {m.lower() for m in spec.measures} if spec.measures else None
            metric_col = next(
                (
                    k for k in result_keys
                    if k.lower() not in measure_keys
                    and k.lower() != "count"
                    and self._is_numeric_value(first_row.get(k))
                    and (allowed_measures is None or k.lower() in allowed_measures)
                ),
                None,
            )

        # If SQL returned row-level data, keep only the intended dimension(s)
        if spec.dimensions and len(dim_cols) > len(spec.dimensions):
            dim_cols = dim_cols[: len(spec.dimensions)]

        return dim_cols, metric_col

    def _aggregate_rows(
        self,
        rows: list[dict],
        dim_cols: list[str],
        metric_col: str,
        aggregation: str,
    ) -> list[dict]:
        """Re-aggregate when SQL returned raw rows instead of GROUP BY results."""
        if not dim_cols or not metric_col:
            return rows

        from collections import defaultdict

        buckets: dict[tuple[str, ...], list[float]] = defaultdict(list)
        for r in rows:
            key = tuple(str(r.get(d, "")).strip() for d in dim_cols)
            if not any(key):
                continue
            try:
                buckets[key].append(float(r.get(metric_col) or 0))
            except (ValueError, TypeError):
                continue

        if len(buckets) >= len(rows):
            return rows

        agg_fn = aggregation.lower()
        aggregated: list[dict] = []
        for key, vals in buckets.items():
            if not vals:
                continue
            if agg_fn == "avg":
                value = sum(vals) / len(vals)
            elif agg_fn == "sum":
                value = sum(vals)
            elif agg_fn == "max":
                value = max(vals)
            elif agg_fn == "min":
                value = min(vals)
            else:
                value = sum(vals)

            row = {dim_cols[i]: key[i] for i in range(len(dim_cols))}
            row[metric_col] = round(value, 2)
            aggregated.append(row)

        aggregated.sort(key=lambda r: float(r.get(metric_col) or 0), reverse=True)
        return aggregated or rows

    def _count_rows_by_dimensions(self, rows: list[dict], dim_cols: list[str]) -> list[dict]:
        """Build COUNT(*) rows when SQL returned unaggregated dimension pairs."""
        from collections import Counter

        counter: Counter[tuple[str, ...]] = Counter()
        for r in rows:
            key = tuple(str(r.get(d, "")).strip() for d in dim_cols)
            if any(key):
                counter[key] += 1

        results = []
        for key, value in counter.most_common():
            row = {dim_cols[i]: key[i] for i in range(len(dim_cols))}
            row["count"] = value
            results.append(row)
        return results

    def _build_charts_from_results(
        self,
        spec: AnalysisSpec,
        numeric_results: list[dict],
    ) -> list:
        """Build bar + table charts directly from SQL rows (never from LLM-invented data)."""
        from app.models.schemas import ChartSpec

        if not numeric_results:
            return [ChartSpec(
                chart_type="table",
                title="No Results",
                data=[{"message": "No data matched your query. Try a different question or check that your data has been processed."}],
                x_field="message",
                y_field="message",
            )]

        first_row = numeric_results[0]
        result_keys = list(first_row.keys())
        dim_cols, metric_col = self._resolve_columns(spec, result_keys, first_row)

        # SQL sometimes returns raw dimension pairs for count questions — aggregate locally
        if (spec.aggregation == "count" or not spec.measures) and dim_cols and "count" not in {k.lower() for k in result_keys}:
            numeric_results = self._count_rows_by_dimensions(numeric_results, dim_cols)
            metric_col = "count"
            first_row = numeric_results[0] if numeric_results else first_row

        if dim_cols and metric_col and len(numeric_results) > 1 and metric_col != "count":
            numeric_results = self._aggregate_rows(
                numeric_results, dim_cols, metric_col, spec.aggregation or "sum",
            )
            first_row = numeric_results[0]

        charts: list[ChartSpec] = []
        if dim_cols and metric_col:
            sorted_rows = sorted(
                numeric_results,
                key=lambda r: float(r.get(metric_col) or 0),
                reverse=True,
            )
            chart_data = []
            for r in sorted_rows[:20]:
                dim_values = [str(r.get(d, "")).strip() for d in dim_cols if r.get(d) not in (None, "")]
                if not dim_values:
                    continue
                x_val = dim_values[0] if len(dim_values) == 1 else " · ".join(dim_values)
                try:
                    y_val = round(float(r.get(metric_col) or 0), 2)
                except (ValueError, TypeError):
                    y_val = 0.0
                chart_data.append({"x": x_val, "y": y_val})

            if chart_data:
                if spec.aggregation == "count" or metric_col.lower() == "count":
                    title = f"Count by {' & '.join(dim_cols)}"
                else:
                    agg_label = (spec.aggregation or "sum").upper()
                    title = f"{agg_label} {metric_col} by {' & '.join(dim_cols)}"
                charts.append(ChartSpec(
                    chart_type="bar",
                    title=title,
                    data=chart_data,
                    x_field="x",
                    y_field="y",
                    color_field=None,
                ))

        # Table shows dimension + count/measure columns
        table_cols = list(dim_cols)
        if metric_col and metric_col not in table_cols:
            table_cols.append(metric_col)
        table_cols = [c for c in table_cols if c]
        if not table_cols:
            table_cols = result_keys
        data = [{c: r.get(c) for c in table_cols} for r in numeric_results[:50]]
        charts.append(ChartSpec(
            chart_type="table",
            title="Data Breakdown",
            data=data,
            x_field=table_cols[0],
            y_field=table_cols[-1],
        ))
        return charts

    def _heuristic_dashboard(
        self,
        spec: AnalysisSpec,
        numeric_results: list[dict],
        textual_results: list[dict],
    ) -> DashboardSpec:
        from app.models.schemas import KPICard

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
                # Numeric measure KPIs — only columns the user asked about
                measure_keys = {m.lower() for m in spec.measures}
                for key in result_keys:
                    if measure_keys and key.lower() not in measure_keys:
                        continue
                    if not self._is_numeric_value(first_row.get(key)):
                        continue
                    vals = [r.get(key) for r in numeric_results if r.get(key) is not None]
                    if vals:
                        try:
                            avg = sum(float(v) for v in vals) / len(vals)
                            kpi_cards.append(KPICard(label=f"Avg {key}", value=f"{avg:.2f}"))
                        except (ValueError, TypeError):
                            pass
                if not kpi_cards:
                    kpi_cards.append(KPICard(label="Groups", value=str(len(numeric_results))))
        else:
            kpi_cards.append(KPICard(label="No Data", value="—"))

        charts = self._build_charts_from_results(spec, numeric_results)

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
