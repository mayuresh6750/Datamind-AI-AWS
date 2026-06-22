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
- measures: numeric columns to aggregate
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

        # Try to match column names mentioned in the question — split on underscores and
        # check if any word token from the column name appears in the question text.
        def _col_score(name: str) -> int:
            tokens = [t for t in name.lower().replace("-", "_").split("_") if len(t) > 2]
            return sum(1 for t in tokens if t in q)

        scored = sorted(profiles, key=lambda p: _col_score(p.name), reverse=True)

        matched_measures = [
            p.name for p in scored
            if p.classification == "numeric" and _col_score(p.name) > 0
        ][:2]
        matched_dims = [
            p.name for p in scored
            if p.classification in ("textual", "ambiguous") and _col_score(p.name) > 0
        ][:2]

        # Fall back to first-N if nothing matched
        measures = matched_measures or [
            p.name for p in profiles if p.classification == "numeric" and p.dtype == "float"
        ][:2] or [p.name for p in profiles if p.classification == "numeric"][:2]
        dimensions = matched_dims or [
            p.name for p in profiles if p.classification in ("textual", "ambiguous")
        ][:2] or ([profiles[0].name] if profiles else [])

        # Pick chart type from question keywords
        if any(k in q for k in ("trend", "over time", "by month", "by week", "by day", "timeline")):
            chart_types = ["line", "bar"]
        elif any(k in q for k in ("count", "how many", "number of", "frequency")):
            chart_types = ["bar", "table"]
        elif any(k in q for k in ("compare", "vs", "versus", "breakdown", "by")):
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
