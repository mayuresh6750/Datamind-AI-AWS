"""Cleaning Executor Agent — executes only user-approved cleaning steps."""
import statistics
from collections import Counter

import structlog

from app.models.schemas import CleaningPlanDecision, CleaningStep

log = structlog.get_logger()


class CleaningExecutorAgent:
    """Executes approved cleaning steps; logs every action for the audit trail."""

    def execute(
        self,
        rows: list[dict],
        steps: list[CleaningStep],
        decision: CleaningPlanDecision,
    ) -> tuple[list[dict], list[dict]]:
        """Returns (cleaned_rows, audit_entries)."""
        approved_ids = set(decision.approved_step_ids)
        approved_steps = [s for s in steps if s.step_id in approved_ids]

        audit: list[dict] = []
        working = [dict(r) for r in rows]

        for step in approved_steps:
            overrides = decision.step_modifications.get(step.step_id, {})
            effective_method = overrides.get("method", step.method)

            before_count = len(working)
            working = self._apply_step(working, step, effective_method)
            after_count = len(working)

            audit.append({
                "step_id": step.step_id,
                "action": step.action,
                "column": step.column,
                "method": effective_method,
                "rationale": step.rationale,
                "confidence": step.confidence,
                "rows_before": before_count,
                "rows_after": after_count,
                "rows_changed": before_count - after_count if step.action == "deduplicate" else step.rows_affected,
            })
            log.info(
                "cleaning_step_executed",
                step_id=step.step_id,
                action=step.action,
                column=step.column,
                rows_before=before_count,
                rows_after=after_count,
            )

        return working, audit

    def _apply_step(self, rows: list[dict], step: CleaningStep, method: str) -> list[dict]:
        if step.action == "deduplicate":
            return self._deduplicate(rows)
        if step.action == "impute" and step.column:
            return self._impute(rows, step.column, method)
        if step.action == "coerce_type" and step.column:
            return self._coerce_type(rows, step.column)
        if step.action == "flag_outlier" and step.column:
            return self._flag_outlier(rows, step.column)
        return rows

    def _deduplicate(self, rows: list[dict]) -> list[dict]:
        seen: set[str] = set()
        result: list[dict] = []
        for row in rows:
            key = str(sorted(row.items()))
            if key not in seen:
                seen.add(key)
                result.append(row)
        return result

    def _impute(self, rows: list[dict], column: str, method: str) -> list[dict]:
        non_null = [r[column] for r in rows if r.get(column) not in (None, "")]

        if not non_null:
            return rows

        if "median" in method.lower():
            try:
                fill_value = statistics.median(float(v) for v in non_null)
            except Exception:
                fill_value = non_null[0]
        elif "mode" in method.lower() or "frequent" in method.lower():
            counts = Counter(non_null)
            fill_value = counts.most_common(1)[0][0]
        else:
            fill_value = non_null[0]

        return [
            {**row, column: fill_value} if row.get(column) in (None, "") else row
            for row in rows
        ]

    def _coerce_type(self, rows: list[dict], column: str) -> list[dict]:
        result = []
        for row in rows:
            val = row.get(column)
            try:
                coerced = float(str(val).replace(",", "")) if val not in (None, "") else None
            except ValueError:
                coerced = val
            result.append({**row, column: coerced})
        return result

    def _flag_outlier(self, rows: list[dict], column: str) -> list[dict]:
        try:
            vals = [float(r[column]) for r in rows if r.get(column) not in (None, "")]
            if len(vals) < 4:
                return rows
            q1 = statistics.quantiles(vals, n=4)[0]
            q3 = statistics.quantiles(vals, n=4)[2]
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            return [
                {**row, f"_outlier_{column}": float(row[column]) < lower or float(row[column]) > upper}
                if row.get(column) not in (None, "") else row
                for row in rows
            ]
        except Exception:
            return rows
