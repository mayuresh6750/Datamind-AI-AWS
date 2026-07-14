"""Intent Agent — parses natural-language question into structured AnalysisSpec."""
import structlog

from app.core.llm import LLMClient
from app.models.schemas import AnalysisSpec, ColumnProfile

log = structlog.get_logger()

_INTENT_PROMPT = """
You are an expert intent parser for a {domain} analytics platform.

The user's question is:
"{question}"

Available columns (name | classification | dtype):
{columns}

Parse the intent into a structured analysis spec. Return ONLY valid JSON matching this schema:
{schema}

Rules:
- original_question: copy the user's question verbatim, exactly as they asked it.
- reasoning: Think step-by-step. Identify: (1) grouping/breakdown columns (dimensions), (2) numeric columns to measure (measures), (3) the mathematical operation.
- dimensions: columns used for grouping/breakdown — "by X", "per X", "Xwise", categorical, or date columns.
- measures: numeric columns to compute an aggregate on. Leave [] if the question is about counts/frequencies only.
- aggregation: the mathematical operation the user is asking for. MUST be one of: "sum", "avg", "count", "max", "min".
  - "total", "sum of", "how much", "overall" → "sum"
  - "average", "mean", "typical" → "avg"
  - "how many", "count", "number of", "frequency", "Xwise" (without explicit numeric measure) → "count"
  - "maximum", "highest", "top", "best", "most" → "max"
  - "minimum", "lowest", "least", "worst", "fewest" → "min"
  - If ambiguous, default to "sum" for numeric columns and "count" for non-numeric.
- filters: any WHERE conditions the user implied (e.g. "in 2023", "for category Electronics").
- suggested_chart_types: 1-3 chart types from [line, bar, table, scatter, pie].
- restatement: rephrase the question in clear domain-specific terms to confirm understanding.
- confidence: float 0.0–1.0 reflecting how clearly the question maps to available columns.

Examples:
  "total quantity ordered by product category" → dimensions: ["Product_Category"], measures: ["Quantity_Ordered"], aggregation: "sum"
  "average order value by city" → dimensions: ["City"], measures: ["Order_Value"], aggregation: "avg"
  "which product had the highest revenue?" → dimensions: ["Product"], measures: ["Revenue"], aggregation: "max"
  "how many orders per region?" → dimensions: ["Region"], measures: [], aggregation: "count"
  "top 5 products by sales" → dimensions: ["Product"], measures: ["Sales"], aggregation: "sum"
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
            # Always preserve the original question exactly
            spec.original_question = question
        except Exception as exc:
            log.warning("intent_llm_failed", error=str(exc))
            spec = self._heuristic_parse(question, profiles)

        log.info("intent_parsed", domain=domain, confidence=spec.confidence, restatement=spec.restatement, aggregation=spec.aggregation)
        return spec

    def _detect_aggregation(self, question: str) -> str:
        """Detect the aggregation type from the user's question using keyword matching."""
        q = question.lower()
        if any(k in q for k in ("total", "sum of", "sum ", "how much", "overall", "cumulative")):
            return "sum"
        if any(k in q for k in ("average", "avg", "mean", "typical")):
            return "avg"
        if any(k in q for k in ("maximum", "highest", "max ", "top ", "best", "most", "largest", "biggest", "peak")):
            return "max"
        if any(k in q for k in ("minimum", "lowest", "min ", "least", "worst", "fewest", "smallest")):
            return "min"
        if any(k in q for k in ("count", "how many", "number of", "frequency", "distribution", "wise", " per ", "breakdown")):
            return "count"
        # Default to sum for numeric questions
        return "sum"

    def _heuristic_parse(self, question: str, profiles: list[ColumnProfile]) -> AnalysisSpec:
        q = question.lower()

        def _col_score(name: str) -> int:
            tokens = [t for t in name.lower().replace("-", "_").split("_") if len(t) > 2]
            return sum(1 for t in tokens if t in q)

        scored = sorted(profiles, key=lambda p: _col_score(p.name), reverse=True)

        # Only genuine numeric (float/int) columns can be measures.
        _numeric_dtypes = {"float", "int", "int64", "float64", "numeric", "integer"}
        matched_measures = [
            p.name for p in scored
            if p.classification == "numeric" and p.dtype in _numeric_dtypes and _col_score(p.name) > 0
        ][:2]
        matched_dims = [
            p.name for p in scored
            if (p.classification in ("structured", "textual", "ambiguous") or p.dtype == "categorical")
            and _col_score(p.name) > 0
        ][:2]

        aggregation = self._detect_aggregation(question)
        is_count_q = aggregation == "count"

        if is_count_q:
            measures: list[str] = []
            dimensions = matched_dims or [
                p.name for p in profiles if p.dtype in ("categorical",)
            ][:2] or [p.name for p in profiles if p.classification in ("structured", "textual", "ambiguous")][:2]
        else:
            measures = matched_measures or [
                p.name for p in profiles if p.classification == "numeric" and p.dtype in _numeric_dtypes
            ][:2]
            dimensions = matched_dims or [
                p.name for p in profiles if p.dtype == "categorical"
            ][:2] or [p.name for p in profiles if p.classification in ("structured", "textual", "ambiguous")][:2]

        if not dimensions and profiles:
            dimensions = [profiles[0].name]

        if any(k in q for k in ("trend", "over time", "by month", "by week", "by day", "timeline")):
            chart_types = ["line", "bar"]
        elif is_count_q or any(k in q for k in ("compare", "vs", "versus", "breakdown", "by")):
            chart_types = ["bar", "table"]
        else:
            chart_types = ["bar", "table"]

        return AnalysisSpec(
            reasoning="Heuristic fallback used due to LLM failure or timeout.",
            original_question=question,
            dimensions=dimensions,
            measures=measures,
            aggregation=aggregation,
            suggested_chart_types=chart_types,
            restatement=question,
            confidence=0.4,
        )
