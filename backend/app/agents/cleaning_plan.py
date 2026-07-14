"""Cleaning Plan Agent — proposes numbered cleaning steps, does NOT execute."""
import structlog

from app.core.llm import LLMClient
from app.models.schemas import CleaningPlan, CleaningStep, ColumnProfile

log = structlog.get_logger()


_PLAN_PROMPT = """
You are a data cleaning planner for a {domain} dataset.

Column profiles (JSON):
{profiles}

Sample rows (first 5, anonymised):
{sample}

Propose a numbered cleaning plan. Each step must have:
- step_id (integer, starting at 1)
- action: one of deduplicate | impute | coerce_type | flag_outlier
- column: column name this step targets (null for row-level ops like deduplicate)
- method: short description of the method
- rationale: why this step is needed
- confidence: float 0.0–1.0 (how confident the agent is this step is needed AND the method is right)
- rows_affected: estimated number of rows affected

IMPUTATION RULES — you MUST follow these when choosing the method:
- classification="numeric"  → use "median imputation"  (preserves distribution, robust to outliers)
- classification="textual"  → use "mode imputation"    (fill with most frequent category value)
- dtype="datetime"          → use "forward fill"        (propagate last known date/time forward)
- classification="ambiguous"→ use "mode imputation"    (safer default for unknown column types)

DO NOT use median imputation for textual/categorical columns such as gender, blood group,
medical condition, city, category, status, or any column with a small set of distinct string values.

CONFIDENCE RULES — confidence reflects both "is this step needed" and "is the method right":
- Very few nulls (null_count < 5% of rows): 0.60–0.70 — step may not be necessary
- Moderate nulls (5–30% of rows): 0.75–0.88 — clear need, good method fit
- High nulls (> 30% of rows): 0.65–0.75 — needed but method reliability is lower
- Categorical column with 2–5 distinct values (e.g. gender, blood type): confidence >= 0.85
- Categorical column with many distinct values (> 50): confidence <= 0.65 (mode is weak signal)
- Ambiguous classification (uncertain about column type): reduce confidence by ~0.08

Return ONLY valid JSON matching the CleaningPlan schema:
{schema}
""".strip()


def _compute_imputation_confidence(
    method: str,
    classification: str,
    null_count: int,
    distinct_count: int,
    total_rows: int,
) -> float:
    """Compute a data-driven confidence score for an imputation step.

    Confidence represents two things combined:
      1. How much does this column need imputation? (driven by null_rate)
      2. How appropriate is the chosen method? (driven by cardinality for mode,
         null_rate for median, ordering assumptions for forward fill)

    All scores are clamped to [0.55, 0.92].
    """
    null_rate = null_count / total_rows if total_rows > 0 else 0.0

    if method == "median imputation":
        # Median is a sound method for numeric data; confidence scales with null_rate
        if null_rate < 0.05:
            # Very few nulls — imputation step barely needed
            base = 0.65
        elif null_rate > 0.40:
            # Column is extremely sparse — median may not represent the true distribution
            base = 0.72
        else:
            # Sweet spot: enough nulls to warrant action, median is reliable
            base = 0.85

    elif method == "mode imputation":
        # Mode works best when there is a clear dominant value (low cardinality)
        if distinct_count <= 5:
            # Very few categories (e.g. Gender: M/F, Blood_Type: A/B/AB/O)
            # → one value almost certainly dominates → high confidence
            base = 0.88
        elif distinct_count <= 20:
            # Moderate cardinality — mode is still meaningful
            base = 0.80
        elif distinct_count <= 50:
            # Higher cardinality — mode exists but is less dominant
            base = 0.70
        else:
            # Many distinct values (e.g. City with 200+ options) — mode is a weak signal
            base = 0.60

        # Penalise if very few nulls (step barely necessary)
        if null_rate < 0.05:
            base -= 0.10

        # Penalise if classification was ambiguous (we weren't certain about the type)
        if classification == "ambiguous":
            base -= 0.08

    elif method == "forward fill":
        # Forward fill depends on data being time-ordered — we can't verify that here
        # Large gaps make forward fill unreliable
        base = 0.65 if null_rate > 0.20 else 0.75

    else:
        base = 0.70

    return round(max(0.55, min(0.92, base)), 2)


class CleaningPlanAgent:
    """Generates a human-reviewable cleaning plan without executing anything."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    async def propose(
        self,
        rows: list[dict],
        profiles: list[ColumnProfile],
        domain: str,
    ) -> CleaningPlan:
        import json

        profile_json = json.dumps([p.model_dump() for p in profiles], indent=2)
        sample_json = json.dumps(rows[:5], indent=2, default=str)

        prompt = _PLAN_PROMPT.format(
            domain=domain,
            profiles=profile_json,
            sample=sample_json,
            schema=CleaningPlan.model_json_schema(),
        )

        llm_error: str | None = None
        try:
            plan = await self.llm.structured_completion(prompt, CleaningPlan, agent_name="cleaning_plan")
            log.info(
                "cleaning_plan_proposed",
                path="llm",
                steps=len(plan.steps),
                domain=domain,
            )
            return plan
        except Exception as exc:
            llm_error = str(exc)
            log.warning(
                "cleaning_plan_llm_failed_using_heuristic",
                error=llm_error,
                domain=domain,
                columns=len(profiles),
                note=(
                    "LLM quota exhausted or timed out — heuristic fallback activated. "
                    "All imputation steps will use rule-based method and confidence selection."
                ),
            )

        plan = self._heuristic_plan(rows, profiles)
        log.info(
            "cleaning_plan_proposed",
            path="heuristic_fallback",
            steps=len(plan.steps),
            domain=domain,
            llm_failure_reason=llm_error,
        )
        return plan

    def _heuristic_plan(self, rows: list[dict], profiles: list[ColumnProfile]) -> CleaningPlan:
        """Fallback: rule-based plan when LLM is unavailable.

        Method selection:
          - dtype="datetime"  → forward fill
          - numeric           → median imputation
          - textual/ambiguous → mode imputation  (never median for categories)

        Confidence is computed dynamically via _compute_imputation_confidence()
        based on null_rate and cardinality — NOT hardcoded.
        """
        steps: list[CleaningStep] = []
        step_id = 1
        total_rows = len(rows)

        # Always propose deduplication
        steps.append(CleaningStep(
            step_id=step_id,
            action="deduplicate",
            column=None,
            method="exact row deduplication",
            rationale="Remove exact duplicate rows present in most real-world exports.",
            confidence=0.95,
            rows_affected=max(1, total_rows // 20),
        ))
        step_id += 1

        for profile in profiles:
            if profile.null_count == 0:
                continue

            null_rate = profile.null_count / total_rows if total_rows > 0 else 0.0
            null_pct = f"{null_rate:.0%}"

            # ── Choose method ─────────────────────────────────────────────────
            if profile.dtype == "datetime":
                method = "forward fill"
                rationale = (
                    f"'{profile.name}' has {profile.null_count} nulls ({null_pct}); "
                    "forward fill propagates the last known date/time value."
                )
            elif profile.classification == "numeric":
                method = "median imputation"
                rationale = (
                    f"'{profile.name}' has {profile.null_count} nulls ({null_pct}); "
                    "median imputation preserves distribution and is robust to outliers."
                )
            else:
                # textual or ambiguous — always mode, never median
                method = "mode imputation"
                rationale = (
                    f"'{profile.name}' has {profile.null_count} nulls ({null_pct}); "
                    f"filling with the most frequent value (mode) is correct for "
                    f"categorical data ({profile.distinct_count} distinct values)."
                )

            # ── Compute dynamic confidence ────────────────────────────────────
            confidence = _compute_imputation_confidence(
                method=method,
                classification=profile.classification,
                null_count=profile.null_count,
                distinct_count=profile.distinct_count,
                total_rows=total_rows,
            )

            log.debug(
                "heuristic_impute_step",
                column=profile.name,
                classification=profile.classification,
                dtype=profile.dtype,
                null_rate=round(null_rate, 3),
                distinct_count=profile.distinct_count,
                method=method,
                confidence=confidence,
            )

            steps.append(CleaningStep(
                step_id=step_id,
                action="impute",
                column=profile.name,
                method=method,
                rationale=rationale,
                confidence=confidence,
                rows_affected=profile.null_count,
            ))
            step_id += 1

        return CleaningPlan(
            steps=steps,
            total_rows_before=total_rows,
            total_rows_after=total_rows,
        )
