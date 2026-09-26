from __future__ import annotations

from typing import Any

import great_expectations as gx
import great_expectations.expectations as gxe
import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json

MIN_ROWS = 5
MAX_ROWS = 5000
MIN_SUMMARY_CHARS = 30
REQUIRED_COLUMNS = ["paper_id", "title", "text_for_embedding"]
MAX_STALE_RATIO = 0.25


def evaluate_freshness_sla(df: pd.DataFrame, settings: Settings) -> dict[str, Any]:
    """Freshness SLA: `is_fresh = False` neu ti le bai co `age_days > threshold` vuot 25%."""
    threshold = settings.freshness_threshold_days
    total_rows = int(len(df))
    published = pd.to_datetime(df["published"], errors="coerce") if total_rows else pd.Series(dtype="datetime64[ns]")
    stale_rows = int((df["age_days"] > threshold).sum()) if total_rows else 0
    stale_ratio = stale_rows / total_rows if total_rows else 1.0
    return {
        "threshold_days": threshold,
        "max_stale_ratio": MAX_STALE_RATIO,
        "latest_published": published.max().strftime("%Y-%m-%d") if published.notna().any() else None,
        "oldest_published": published.min().strftime("%Y-%m-%d") if published.notna().any() else None,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": round(stale_ratio, 4),
        "is_fresh": total_rows > 0 and stale_ratio <= MAX_STALE_RATIO,
    }


def _build_expectations() -> list[gxe.Expectation]:
    return [
        gxe.ExpectTableRowCountToBeBetween(min_value=MIN_ROWS, max_value=MAX_ROWS),
        *[gxe.ExpectColumnValuesToNotBeNull(column=column) for column in REQUIRED_COLUMNS],
        gxe.ExpectColumnValuesToBeUnique(column="paper_id"),
        gxe.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=MIN_SUMMARY_CHARS),
    ]


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Chay 4 expectation GX 1.x (Ephemeral Context) + Freshness SLA, ghi report vao `data/quality/`.

    `success` phan anh ket qua GX; freshness la canh bao rieng (`freshness.is_fresh`).
    """
    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
    # GX khong validate duoc cot list (authors/categories) -> chi dua cot scalar vao batch
    scalar_df = df[[column for column in df.columns if column not in {"authors", "categories"}]]
    batch = batch_def.get_batch(batch_parameters={"dataframe": scalar_df})

    suite = context.suites.add(gx.ExpectationSuite(name=f"papers_{report_name}_suite"))
    for expectation in _build_expectations():
        suite.add_expectation(expectation)
    validation = batch.validate(suite)

    checks = [
        {
            "expectation": result.expectation_config.type,
            "column": result.expectation_config.kwargs.get("column"),
            "success": bool(result.success),
            "observed_value": result.result.get("observed_value"),
            "unexpected_count": result.result.get("unexpected_count"),
        }
        for result in validation.results
    ]
    freshness = evaluate_freshness_sla(df, settings)
    report = {
        "report_name": report_name,
        "generated_at": now_utc().isoformat(),
        "success": bool(validation.success),
        "row_count": int(len(df)),
        "failed_expectations": [check for check in checks if not check["success"]],
        "checks": checks,
        "freshness": freshness,
    }
    write_json(settings.paths.quality_dir / f"{report_name}_quality_report.json", report)
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Tong hop freshness report va ghi JSON vao `report_path`."""
    payload = {"generated_at": now_utc().isoformat(), **evaluate_freshness_sla(df, settings)}
    write_json(report_path, payload)
    return payload
