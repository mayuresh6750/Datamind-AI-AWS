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

        spec = await self.llm.structured_completion(prompt, AnalysisSpec, agent_name="intent")
        log.info("intent_parsed", domain=domain, confidence=spec.confidence, restatement=spec.restatement)
        return spec
