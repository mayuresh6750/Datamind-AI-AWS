"""Ingestion Agent — format detection, parsing, column profiling, merge plan."""
import csv
import io
import json
from typing import Any

import structlog

from app.core.llm import LLMClient
from app.models.schemas import ColumnProfile, MergePlan

log = structlog.get_logger()

NUMERIC_DTYPES = {"int", "int64", "float", "float64", "bool", "datetime64", "date"}
MAX_CARDINALITY_FOR_STRUCTURED = 50
MIN_AVG_LENGTH_FOR_TEXTUAL = 40


class IngestionAgent:
    """Detects format, parses data, profiles columns, proposes merge plan."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm or LLMClient()

    def detect_format(self, filename: str, content: bytes) -> str:
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext in ("csv", "xlsx", "json", "parquet"):
            return ext
        # fallback: sniff CSV
        try:
            sample = content[:2048].decode("utf-8", errors="replace")
            csv.Sniffer().sniff(sample)
            return "csv"
        except Exception:
            return "unknown"

    def parse_csv(self, content: bytes) -> list[dict]:
        text = content.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        return list(reader)

    def parse_json(self, content: bytes) -> list[dict]:
        data = json.loads(content)
        if isinstance(data, list):
            return data
        return [data]

    def profile_columns(self, rows: list[dict]) -> list[ColumnProfile]:
        if not rows:
            return []

        profiles: list[ColumnProfile] = []
        columns = list(rows[0].keys())

        for col in columns:
            values = [r.get(col) for r in rows]
            non_null = [v for v in values if v is not None and v != ""]
            null_count = len(values) - len(non_null)
            distinct_vals = set(str(v) for v in non_null)
            distinct_count = len(distinct_vals)

            # Determine if numeric
            numeric_count = 0
            total_str_len = 0
            for v in non_null:
                try:
                    float(str(v).replace(",", ""))
                    numeric_count += 1
                except ValueError:
                    total_str_len += len(str(v))

            numeric_ratio = numeric_count / len(non_null) if non_null else 0
            avg_length = total_str_len / (len(non_null) - numeric_count) if (len(non_null) - numeric_count) > 0 else 0.0

            if numeric_ratio >= 0.9:
                classification = "numeric"
                dtype = "float"
            elif distinct_count <= MAX_CARDINALITY_FOR_STRUCTURED:
                classification = "numeric"
                dtype = "categorical"
            elif avg_length >= MIN_AVG_LENGTH_FOR_TEXTUAL or distinct_count > 0.5 * len(rows):
                classification = "textual"
                dtype = "text"
            else:
                classification = "ambiguous"
                dtype = "text"

            profiles.append(ColumnProfile(
                name=col,
                dtype=dtype,
                null_count=null_count,
                distinct_count=distinct_count,
                avg_length=avg_length if avg_length > 0 else None,
                classification=classification,
            ))

        return profiles

    def propose_merge_plan(self, file_profiles: list[tuple[str, list[ColumnProfile]]]) -> MergePlan:
        if len(file_profiles) == 1:
            return MergePlan(
                strategy="single",
                confidence=0.99,
                column_profiles=file_profiles[0][1],
            )

        # Check if all files share the same columns (UNION candidate)
        all_col_sets = [set(p.name for p in profiles) for _, profiles in file_profiles]
        if all(s == all_col_sets[0] for s in all_col_sets):
            all_profiles = file_profiles[0][1]
            return MergePlan(strategy="union", confidence=0.92, column_profiles=all_profiles)

        # Different schemas — JOIN candidate; find common key column
        common_cols = all_col_sets[0].intersection(*all_col_sets[1:])
        join_key = next(iter(common_cols), None)
        all_profiles = [p for _, profiles in file_profiles for p in profiles]
        return MergePlan(
            strategy="join" if join_key else "separate",
            join_key=join_key,
            confidence=0.75 if join_key else 0.55,
            column_profiles=all_profiles,
        )

    def to_json_records(self, rows: list[dict]) -> list[dict]:
        return rows
