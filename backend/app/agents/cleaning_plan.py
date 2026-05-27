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
- method: short description of the method (e.g. "median imputation", "IQR outlier flagging")
- rationale: why this step is needed
- confidence: float 0.0–1.0 (how confident the agent is this step is needed)
- rows_affected: estimated number of rows affected

Return ONLY valid JSON matching the CleaningPlan schema:
{schema}
""".strip()


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

        try:
            plan = await self.llm.structured_completion(prompt, CleaningPlan, agent_name="cleaning_plan")
        except Exception as exc:
            log.warning("cleaning_plan_llm_failed", error=str(exc))
            plan = self._heuristic_plan(rows, profiles)

        log.info("cleaning_plan_proposed", steps=len(plan.steps), domain=domain)
        return plan

    def _heuristic_plan(self, rows: list[dict], profiles: list[ColumnProfile]) -> CleaningPlan:
        """Fallback: rule-based plan when LLM is unavailable."""
        steps: list[CleaningStep] = []
        step_id = 1

        # Always propose deduplication
        steps.append(CleaningStep(
            step_id=step_id,
            action="deduplicate",
            column=None,
            method="exact row deduplication",
            rationale="Remove exact duplicate rows present in most real-world exports.",
            confidence=0.95,
            rows_affected=max(1, len(rows) // 20),
        ))
        step_id += 1

        for profile in profiles:
            if profile.null_count > 0 and profile.classification == "numeric":
                steps.append(CleaningStep(
                    step_id=step_id,
                    action="impute",
                    column=profile.name,
                    method="median imputation",
                    rationale=f"Column has {profile.null_count} nulls; median imputation preserves distribution.",
                    confidence=0.85,
                    rows_affected=profile.null_count,
                ))
                step_id += 1
            elif profile.null_count > 0 and profile.classification == "textual":
                steps.append(CleaningStep(
                    step_id=step_id,
                    action="impute",
                    column=profile.name,
                    method="mode imputation",
                    rationale=f"Column has {profile.null_count} nulls; fill with most frequent value.",
                    confidence=0.75,
                    rows_affected=profile.null_count,
                ))
                step_id += 1

        return CleaningPlan(
            steps=steps,
            total_rows_before=len(rows),
            total_rows_after=len(rows),
        )
