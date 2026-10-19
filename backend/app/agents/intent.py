"""Intent Agent — parses natural-language question into structured AnalysisSpec."""
import re
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
  - "how many", "count", "number of", "frequency" → "count"
  - "Xwise" / "X wise" WITH an explicit numeric measure (e.g. "lab_test wise average test_cost") → use the measure's aggregation ("avg"), NOT count
  - "Xwise" / "X wise" WITHOUT a numeric measure (e.g. "region wise count") → "count"
  - "maximum", "highest", "top", "best", "most" → "max"
  - "minimum", "lowest", "least", "worst", "fewest" → "min"
  - If ambiguous, default to "sum" for numeric columns and "count" for non-numeric.
- filters: any WHERE conditions the user implied (e.g. "in 2023", "for category Electronics").
- semantic_filter_concept: When the question filters, qualifies, or narrows down data using a qualitative concept, symptom, issue, complaint, or sentiment that lives in free-text columns (reviews, feedback, notes, comments) rather than an explicit categorical column (e.g. "battery issues", "delivery delays", "post-surgery infections", "billing disputes"), extract that exact semantic concept phrase here. If there is no free-text semantic concept, leave as null.
- suggested_chart_types: 1-3 chart types from [line, bar, table, scatter, pie].
- restatement: rephrase the question in clear domain-specific terms to confirm understanding.
- confidence: float 0.0–1.0 reflecting how clearly the question maps to available columns.

Examples:
  "total revenue lost to battery issues" → dimensions: [], measures: ["Revenue"], aggregation: "sum", semantic_filter_concept: "battery issues"
  "how many patients readmitted due to post-surgery infections?" → dimensions: [], measures: [], aggregation: "count", semantic_filter_concept: "post-surgery infections"
  "average order value for customers complaining about delivery delays" → dimensions: [], measures: ["Order_Value"], aggregation: "avg", semantic_filter_concept: "delivery delays"
  "total quantity ordered by product category" → dimensions: ["Product_Category"], measures: ["Quantity_Ordered"], aggregation: "sum", semantic_filter_concept: null
  "average order value by city" → dimensions: ["City"], measures: ["Order_Value"], aggregation: "avg", semantic_filter_concept: null
  "which product had the highest revenue?" → dimensions: ["Product"], measures: ["Revenue"], aggregation: "max", semantic_filter_concept: null
  "how many orders per region?" → dimensions: ["Region"], measures: [], aggregation: "count", semantic_filter_concept: null
  "top 5 products by sales" → dimensions: ["Product"], measures: ["Sales"], aggregation: "sum", semantic_filter_concept: null
  "lab_test wise average test_cost" → dimensions: ["Lab_Test"], measures: ["Test_Cost"], aggregation: "avg", semantic_filter_concept: null
  "citywise diagnosis chart with counts" → dimensions: ["City", "Diagnosis"], measures: [], aggregation: "count", semantic_filter_concept: null
  IMPORTANT: When the user says "X wise", "X-wise", or "Xwise" (no space), X is the primary grouping dimension.
  If they also name another categorical column (e.g. "citywise diagnosis"), include both dimensions with count aggregation.
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
            spec.original_question = question
            spec = self._normalize_spec(question, profiles, spec)
        except Exception as exc:
            log.warning("intent_llm_failed", error=str(exc))
            spec = self._heuristic_parse(question, profiles)

        log.info(
            "intent_parsed",
            domain=domain,
            confidence=spec.confidence,
            restatement=spec.restatement,
            aggregation=spec.aggregation,
            dimensions=spec.dimensions,
            measures=spec.measures,
        )
        return spec

    def _normalize_question(self, question: str) -> str:
        return question.lower().replace("-", "_").replace(" ", "_")

    def _question_tokens(self, question: str) -> set[str]:
        """Tokenize question and expand underscore compounds (test_cost → test, cost)."""
        tokens = set(re.findall(r"\w+", question.lower()))
        expanded = set(tokens)
        for token in tokens:
            if "_" in token:
                expanded.update(part for part in token.split("_") if len(part) > 2)
        return expanded

    def _column_in_question(self, name: str, question: str) -> bool:
        return name.lower().replace("-", "_") in self._normalize_question(question)

    def _extract_explicit_measure(self, question: str, profiles: list[ColumnProfile]) -> str | None:
        """Parse 'average test_cost' / 'sum of revenue' → matching column name."""
        m = re.search(
            r"\b(?:average|avg|mean|sum|total|maximum|max|minimum|min|count)\s+(?:of\s+)?(\w+(?:_\w+)*)",
            question,
            re.I,
        )
        candidates: list[str] = []
        if m:
            candidates.append(m.group(1).lower().replace("-", "_"))

        q_norm = self._normalize_question(question)
        for p in profiles:
            norm = p.name.lower().replace("-", "_")
            if norm in q_norm:
                candidates.append(norm)

        for phrase in candidates:
            for p in profiles:
                if p.name.lower().replace("-", "_") == phrase:
                    return p.name
            best: tuple[int, str] | None = None
            phrase_tokens = {t for t in phrase.split("_") if len(t) > 2}
            for p in profiles:
                name_tokens = {t for t in p.name.lower().replace("-", "_").split("_") if len(t) > 2}
                overlap = len(phrase_tokens & name_tokens)
                if overlap and (best is None or overlap > best[0]):
                    best = (overlap, p.name)
            if best:
                return best[1]
        return None

    def _is_measure_column(self, profile: ColumnProfile) -> bool:
        _numeric_dtypes = {"float", "int", "int64", "float64", "numeric", "integer"}
        return profile.classification == "numeric" and profile.dtype in _numeric_dtypes

    def _is_categorical_column(self, profile: ColumnProfile) -> bool:
        return (
            profile.classification in ("structured", "textual", "ambiguous")
            or profile.dtype in ("categorical", "text", "datetime", "date")
        )

    def _extract_mentioned_dimensions(
        self,
        question: str,
        profiles: list[ColumnProfile],
        *,
        exclude: set[str] | None = None,
    ) -> list[str]:
        """Other categorical columns explicitly named in the question (e.g. diagnosis in citywise diagnosis)."""
        excluded = {e.lower() for e in (exclude or set())}
        mentioned: list[str] = []
        for p in profiles:
            if p.name.lower() in excluded:
                continue
            if self._is_date_column(p.name, profiles) and not self._question_mentions_time(question):
                continue
            if self._is_categorical_column(p) and self._column_in_question(p.name, question):
                mentioned.append(p.name)
        return mentioned

    def _normalize_spec(self, question: str, profiles: list[ColumnProfile], spec: AnalysisSpec) -> AnalysisSpec:
        """Apply deterministic corrections for wise/count patterns and explicit measures."""
        wise_dim = self._extract_wise_dimension(question, profiles)
        explicit_measure = self._extract_explicit_measure(question, profiles)
        aggregation = self._detect_aggregation(question) if self._has_explicit_aggregation(question) else spec.aggregation

        if self._question_requests_count(question):
            spec.aggregation = "count"
            spec.measures = []
        elif explicit_measure and aggregation != "count":
            spec.measures = [explicit_measure]
            spec.aggregation = aggregation

        if wise_dim:
            secondary = self._extract_mentioned_dimensions(question, profiles, exclude={wise_dim})
            spec.dimensions = [wise_dim, *secondary]
            if self._question_requests_count(question) or not spec.measures:
                spec.measures = []
                spec.aggregation = "count"
        elif len(spec.dimensions) > 1 and not self._question_mentions_time(question):
            spec.dimensions = [
                d for d in spec.dimensions
                if not self._is_date_column(d, profiles)
            ] or spec.dimensions[:1]

        if self._has_explicit_aggregation(question):
            spec.aggregation = self._detect_aggregation(question)
            if spec.aggregation == "count":
                spec.measures = []

        if not spec.semantic_filter_concept:
            spec.semantic_filter_concept = self._extract_semantic_concept(question, profiles)

        return spec

    def _extract_semantic_concept(self, question: str, profiles: list[ColumnProfile]) -> str | None:
        """Extract semantic qualifying concepts (e.g. 'battery issues', 'delivery delays') from question."""
        patterns = [
            r"\b(?:due to|lost to|complaining about|complained about|issues? with|related to|because of|suffering from)\s+([a-zA-Z0-9_\s\-]+?)(?:\?|$|\bfor\b|\bby\b|\bin\b)",
            r"\b(?:about|with)\s+([a-zA-Z0-9_\s\-]+?\s+(?:issues?|problems?|delays?|infections?|complaints?|defects?|errors?|faults?))(?:\?|$|\bfor\b|\bby\b|\bin\b)",
        ]
        col_names_lower = {p.name.lower() for p in profiles}
        for pattern in patterns:
            m = re.search(pattern, question, re.I)
            if m:
                concept = m.group(1).strip().strip("'\"")
                if concept.lower() not in col_names_lower and len(concept) > 2:
                    return concept
        return None

    @staticmethod
    def _question_requests_count(question: str) -> bool:
        q = question.lower()
        return any(k in q for k in ("count", "counts", "how many", "number of", "frequency"))

    @staticmethod
    def _has_explicit_aggregation(question: str) -> bool:
        q = question.lower()
        return any(k in q for k in ("average", "avg", "mean", "total", "sum", "count", "maximum", "minimum", "highest", "lowest"))

    @staticmethod
    def _question_mentions_time(question: str) -> bool:
        q = question.lower()
        return any(k in q for k in ("date", "time", "month", "week", "day", "year", "timeline", "trend", "over time"))

    @staticmethod
    def _is_date_column(name: str, profiles: list[ColumnProfile]) -> bool:
        for p in profiles:
            if p.name.lower() == name.lower():
                return p.dtype in ("datetime", "date") or "date" in p.name.lower() or "time" in p.name.lower()
        return "date" in name.lower() or "time" in name.lower()

    def _extract_wise_dimension(self, question: str, profiles: list[ColumnProfile]) -> str | None:
        """Parse 'citywise diagnosis', 'lab_test wise', or 'city wise' → primary grouping column."""
        patterns = [
            r"(\w+(?:_\w+)*)\s+wise\b",
            r"(\w+)(?:wise)\b",
        ]
        phrase: str | None = None
        for pattern in patterns:
            m = re.search(pattern, question, re.I)
            if m:
                phrase = m.group(1).lower().replace("-", "_")
                break
        if not phrase:
            return None

        for prefix in ("give_me_", "show_me_", "get_me_", "tell_me_", "create_a_", "create_"):
            if phrase.startswith(prefix):
                phrase = phrase[len(prefix):]

        best: tuple[int, str] | None = None
        for p in profiles:
            normalized = p.name.lower().replace("-", "_")
            if phrase == normalized:
                return p.name
            phrase_tokens = {t for t in phrase.split("_") if len(t) > 2}
            name_tokens = {t for t in normalized.split("_") if len(t) > 2}
            overlap = len(phrase_tokens & name_tokens)
            if overlap and (best is None or overlap > best[0]):
                best = (overlap, p.name)
        return best[1] if best else None

    def _match_measures(self, question: str, profiles: list[ColumnProfile]) -> list[str]:
        explicit = self._extract_explicit_measure(question, profiles)
        if explicit:
            return [explicit]

        q_tokens = self._question_tokens(question)

        def _col_score(name: str) -> int:
            tokens = [t for t in name.lower().replace("-", "_").split("_") if len(t) > 2]
            return sum(1 for t in tokens if t in q_tokens)

        scored = sorted(
            (p for p in profiles if self._is_measure_column(p)),
            key=lambda p: (_col_score(p.name), self._column_in_question(p.name, question)),
            reverse=True,
        )
        matched = [p.name for p in scored if _col_score(p.name) > 0 or self._column_in_question(p.name, question)]
        if matched:
            return matched[:1]

        # No explicit match — do not guess; caller may treat as count query
        return []

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
        # "wise" alone implies count; "X wise average Y" is handled via explicit average above
        if any(k in q for k in ("count", "counts", "how many", "number of", "frequency", "distribution")):
            return "count"
        if re.search(r"\b\w+(?:_\w+)*(?:\s+wise|wise)\b", q) and not self._has_explicit_aggregation(question):
            return "count"
        if any(k in q for k in (" per ", "breakdown")):
            return "count"
        # Default to sum for numeric questions
        return "sum"

    def _heuristic_parse(self, question: str, profiles: list[ColumnProfile]) -> AnalysisSpec:
        q = question.lower()
        q_tokens = self._question_tokens(question)

        def _col_score(name: str) -> int:
            tokens = [t for t in name.lower().replace("-", "_").split("_") if len(t) > 2]
            return sum(1 for t in tokens if t in q_tokens)

        wise_dim = self._extract_wise_dimension(question, profiles)
        explicit_measure = self._extract_explicit_measure(question, profiles)
        aggregation = self._detect_aggregation(question)
        is_count_q = aggregation == "count" or self._question_requests_count(question)

        if wise_dim:
            secondary = self._extract_mentioned_dimensions(question, profiles, exclude={wise_dim})
            dimensions = [wise_dim, *secondary]
            if is_count_q:
                measures = []
                aggregation = "count"
            else:
                measures = [explicit_measure] if explicit_measure else self._match_measures(question, profiles)
        else:
            scored = sorted(profiles, key=lambda p: _col_score(p.name), reverse=True)
            matched_measures = [
                p.name for p in scored
                if self._is_measure_column(p) and (_col_score(p.name) > 0 or self._column_in_question(p.name, question))
            ][:1]
            if explicit_measure:
                matched_measures = [explicit_measure]
            matched_dims = [
                p.name for p in scored
                if (p.classification in ("structured", "textual", "ambiguous") or p.dtype == "categorical")
                and _col_score(p.name) > 0
                and not self._is_date_column(p.name, profiles)
            ][:1]
            if is_count_q:
                measures = []
                mentioned = self._extract_mentioned_dimensions(question, profiles)
                dimensions = mentioned or matched_dims or [
                    p.name for p in profiles if p.dtype in ("categorical",)
                ][:2] or [p.name for p in profiles if p.classification in ("structured", "textual", "ambiguous")][:2]
            else:
                measures = matched_measures
                dimensions = matched_dims or [
                    p.name for p in profiles if p.dtype == "categorical"
                ][:1] or [p.name for p in profiles if p.classification in ("structured", "textual", "ambiguous")][:1]

        if not dimensions and profiles:
            dimensions = [profiles[0].name]

        if any(k in q for k in ("trend", "over time", "by month", "by week", "by day", "timeline")):
            chart_types = ["line", "bar"]
        elif is_count_q or any(k in q for k in ("compare", "vs", "versus", "breakdown", "by")):
            chart_types = ["bar", "table"]
        else:
            chart_types = ["bar", "table"]

        semantic_concept = self._extract_semantic_concept(question, profiles)

        return AnalysisSpec(
            reasoning="Heuristic fallback used due to LLM failure or timeout.",
            original_question=question,
            dimensions=dimensions,
            measures=measures,
            aggregation=aggregation,
            suggested_chart_types=chart_types,
            restatement=question,
            confidence=0.4,
            semantic_filter_concept=semantic_concept,
        )
