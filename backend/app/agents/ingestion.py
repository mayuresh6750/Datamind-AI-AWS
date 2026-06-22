"""Ingestion Agent — format detection, parsing, column profiling, merge plan."""
import csv
import io
import json
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import structlog
from openpyxl import load_workbook

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
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        # csv.DictReader stores overflow values under key None; strip those artifacts
        return [{k: v for k, v in row.items() if k is not None} for row in reader]

    def parse_json(self, content: bytes) -> list[dict]:
        data = json.loads(content)
        if isinstance(data, list):
            return data
        return [data]

    def parse_xlsx(self, content: bytes) -> list[dict]:
        workbook = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        rows: list[dict] = []

        for sheet in workbook.worksheets:
            values = list(sheet.iter_rows(values_only=True))
            if not values:
                continue

            headers = [str(value).strip() if value is not None else "" for value in values[0]]
            if not any(headers):
                continue

            for raw_row in values[1:]:
                if raw_row is None or not any(value is not None and value != "" for value in raw_row):
                    continue

                row = {
                    header: value
                    for header, value in zip(headers, raw_row, strict=False)
                    if header
                }
                if row:
                    rows.append(row)

        return rows

    def parse_parquet(self, content: bytes) -> list[dict]:
        table = pq.read_table(pa.BufferReader(content))
        return table.to_pylist()

    def parse_content(self, fmt: str, content: bytes) -> list[dict]:
        if fmt == "csv":
            return self.parse_csv(content)
        if fmt == "json":
            return self.parse_json(content)
        if fmt == "xlsx":
            return self.parse_xlsx(content)
        if fmt == "parquet":
            return self.parse_parquet(content)
        raise ValueError(f"Unsupported file format: {fmt}")

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
            elif avg_length >= MIN_AVG_LENGTH_FOR_TEXTUAL or distinct_count > 0.5 * len(rows):
                classification = "textual"
                dtype = "text"
            elif distinct_count <= MAX_CARDINALITY_FOR_STRUCTURED:
                classification = "numeric"
                dtype = "categorical"
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

    def propose_merge_plan(
        self,
        file_profiles: list[tuple[str, list[ColumnProfile]]],
        all_rows: list[dict] | None = None,
    ) -> MergePlan:
        if len(file_profiles) == 1:
            return MergePlan(
                strategy="single",
                confidence=0.99,
                column_profiles=file_profiles[0][1],
            )

        # Check if all files share the same columns (UNION candidate)
        all_col_sets = [set(p.name for p in profiles) for _, profiles in file_profiles]
        if all(s == all_col_sets[0] for s in all_col_sets):
            # Recompute profiles over the combined row set so stats (null_count,
            # distinct_count, avg_length, classification) reflect all files stacked
            # together, not just the first file.
            all_profiles = self.profile_columns(all_rows) if all_rows is not None else file_profiles[0][1]
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
