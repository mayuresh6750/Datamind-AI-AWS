"""Intent Agent — parses natural-language question into structured AnalysisSpec."""
import structlog

from app.core.llm import LLMClient
from app.models.schemas import AnalysisSpec, ColumnProfile

log = structlog.get_logger()

_INTENT_PROMPT = """
You are an intent parser for a {domain} analytics platform.

The user's question is:
"{question}"

Available columns (name | classification | dtype):
{columns}

Parse the intent into a structured analysis spec. Return ONLY valid JSON matching this schema:
{schema}

Rules:
- dimensions: grouping columns (categorical, date/time, or textual classification columns)
- measures: numeric columns to aggregate with AVG/SUM
  IMPORTANT — "Xwise", "X wise", "by X", "per X" means GROUP BY X. Set measures: [] and
  use COUNT(*) automatically. Do NOT include unrelated numeric columns as measures.
  Examples:
    "citywise lab_test"        → dimensions: ["City","Lab_Test"],  measures: []
    "lab_test wise test_cost"  → dimensions: ["Lab_Test"],         measures: ["Test_Cost"]
    "agewise test_cost"        → dimensions: ["Age"],              measures: ["Test_Cost"]
  Only add a numeric column to measures when the question explicitly asks to aggregate it
  (e.g. "average cost", "total bill", "sum of amount").
- suggested_chart_types: 1-3 chart types from [line, bar, table, scatter, pie]
- restatement: rephrase the question in domain-specific terms to confirm understanding
- confidence: float 0.0–1.0 reflecting how clearly the question maps to available columns
""".strip()


class IntentAgent:
    """Parses user intent into a structured AnalysisSpec for the Analysis Agent."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def parse(
        self,
        question: str,
        profiles: list[ColumnProfile],
        domain: str,
    ) -> AnalysisSpec:
        col_lines = "\n".join(f"{p.name} | {p.classification} | {p.dtype}" for p in profiles)

        prompt = _INTENT_PROMPT.format(
            domain=domain,
            question=question,
            columns=col_lines,
            schema=AnalysisSpec.model_json_schema(),
        )

        try:
            spec = await self.llm.structured_completion(prompt, AnalysisSpec, agent_name="intent")
        except Exception as exc:
            log.warning("intent_llm_failed", error=str(exc))
            spec = self._heuristic_parse(question, profiles)

        log.info("intent_parsed", domain=domain, confidence=spec.confidence, restatement=spec.restatement)
        return spec

    def _heuristic_parse(self, question: str, profiles: list[ColumnProfile]) -> AnalysisSpec:
        q = question.lower()

        def _col_score(name: str) -> int:
            tokens = [t for t in name.lower().replace("-", "_").split("_") if len(t) > 2]
            return sum(1 for t in tokens if t in q)

        scored = sorted(profiles, key=lambda p: _col_score(p.name), reverse=True)

        # Only genuine numeric (float/int) columns can be measures — NOT categoricals.
        # A column with classification="numeric" and dtype="categorical" (e.g. Department)
        # must be treated as a dimension, not a measure; doing AVG("Department") would crash.
        _numeric_dtypes = {"float", "int", "int64", "float64", "numeric"}
        matched_measures = [
            p.name for p in scored
            if p.classification == "numeric" and p.dtype in _numeric_dtypes and _col_score(p.name) > 0
        ][:2]
        matched_dims = [
            p.name for p in scored
            if (p.classification in ("textual", "ambiguous") or p.dtype == "categorical")
            and _col_score(p.name) > 0
        ][:2]

        # Detect count-type questions — no numeric measure needed, just GROUP BY dimensions.
        # "citywise", "lab_test wise", "city wise" all mean GROUP BY → COUNT(*).
        import re as _re
        _has_wise = bool(_re.search(r'\bwise\b', q))
        is_count_q = _has_wise or any(k in q for k in (
            "count", "how many", "number of", "frequency", "distribution",
            "wise count", "per ", "breakdown",
        ))

        if is_count_q:
            measures: list[str] = []
            dimensions = matched_dims or [
                p.name for p in profiles if p.dtype == "categorical"
            ][:2] or [p.name for p in profiles if p.classification in ("textual", "ambiguous")][:2]
        else:
            measures = matched_measures or [
                p.name for p in profiles if p.classification == "numeric" and p.dtype in _numeric_dtypes
            ][:2]
            dimensions = matched_dims or [
                p.name for p in profiles if p.dtype == "categorical"
            ][:2] or [p.name for p in profiles if p.classification in ("textual", "ambiguous")][:2]

        if not dimensions and profiles:
            dimensions = [profiles[0].name]

        if any(k in q for k in ("trend", "over time", "by month", "by week", "by day", "timeline")):
            chart_types = ["line", "bar"]
        elif is_count_q or any(k in q for k in ("compare", "vs", "versus", "breakdown", "by")):
            chart_types = ["bar", "table"]
        else:
            chart_types = ["bar", "table"]

        return AnalysisSpec(
            dimensions=dimensions,
            measures=measures,
            suggested_chart_types=chart_types,
            restatement=question,
            confidence=0.4,
        )
