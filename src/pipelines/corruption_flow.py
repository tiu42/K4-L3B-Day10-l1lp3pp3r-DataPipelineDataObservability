from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from core.config import Settings, load_settings
from core.utils import now_utc, read_json, write_csv
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import format_metrics_comparison, generate_corruption_report
from retrieval.index import LocalEmbeddingIndex

logger = logging.getLogger(__name__)


def _save_dataframe(df: pd.DataFrame, csv_path, json_path) -> None:
    write_csv(df, csv_path)
    df.to_json(json_path, orient="records", indent=2, force_ascii=False)


def repair_from_raw_snapshot(settings: Settings) -> pd.DataFrame:
    """Idempotent repair: rebuild clean dataset tu raw snapshot bat bien, bo qua moi ban da bi hong.

    Chay lai bao nhieu lan cung cho cung ket qua vi chi phu thuoc `raw_records_json`.
    """
    paths = settings.paths
    repaired = build_clean_dataframe(load_raw_records(paths.raw_records_json), now_utc())
    _save_dataframe(repaired, paths.repaired_clean_csv, paths.repaired_clean_json)
    logger.info("Repaired %d rows from raw snapshot %s", len(repaired), paths.raw_records_json)
    return repaired


def run_corruption_flow_pipeline(settings: Settings) -> dict[str, Any]:
    """Corrupt -> evaluate (silent failure) -> repair tu raw snapshot -> re-evaluate -> compare."""
    paths = settings.paths
    if not paths.baseline_metrics.exists() or not paths.clean_json.exists():
        raise FileNotFoundError("Baseline artifacts missing, run `python script/run_phase1.py` first.")

    # 1. Baseline
    baseline_metrics = read_json(paths.baseline_metrics)
    clean_df = pd.read_json(paths.clean_json)

    # 2-3. Corrupt + save artifacts
    corrupted_df = corrupt_clean_dataframe(clean_df, paths.corruption_log)
    _save_dataframe(corrupted_df, paths.corrupted_clean_csv, paths.corrupted_clean_json)

    # 4-5. Silent failure: quality gate chi quan sat (khong chan) de do muc suy giam khi data ban lot vao index
    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness = build_freshness_report(
        corrupted_df, settings, paths.quality_dir / "corrupted_freshness_report.json"
    )
    if not corrupted_quality["success"]:
        logger.warning(
            "Quality gate FAILED on corrupted data (%d failed expectations) - indexing anyway to measure impact",
            len(corrupted_quality["failed_expectations"]),
        )
    corrupted_index = LocalEmbeddingIndex.build(corrupted_df, settings, paths.corrupted_embeddings_json)
    corrupted_metrics = evaluate_pipeline(
        settings, corrupted_index, paths.eval_testset, paths.corrupted_metrics, paths.corrupted_answers
    ).summary

    # 6. Repair tu raw snapshot, lan nay quality gate phai pass truoc khi index
    repaired_df = repair_from_raw_snapshot(settings)
    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness = build_freshness_report(
        repaired_df, settings, paths.quality_dir / "repaired_freshness_report.json"
    )
    if not repaired_quality["success"]:
        raise RuntimeError("Repaired dataset still fails the quality gate, check the raw snapshot.")

    # 7. Re-evaluate
    repaired_index = LocalEmbeddingIndex.build(repaired_df, settings, paths.repaired_embeddings_json)
    repaired_metrics = evaluate_pipeline(
        settings, repaired_index, paths.eval_testset, paths.repaired_metrics, paths.repaired_answers
    ).summary

    # 8. Comparison report
    generate_corruption_report(
        paths.comparison_report,
        baseline_metrics,
        corrupted_metrics,
        repaired_metrics,
        corrupted_quality,
        repaired_quality,
        corrupted_freshness,
        repaired_freshness,
    )
    return {
        "baseline": baseline_metrics,
        "corrupted": corrupted_metrics,
        "repaired": repaired_metrics,
        "corrupted_quality_success": corrupted_quality["success"],
        "repaired_quality_success": repaired_quality["success"],
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = load_settings()
    result = run_corruption_flow_pipeline(settings)
    print()
    print(format_metrics_comparison(result["baseline"], result["corrupted"], result["repaired"]))
    print()
    print(
        f"Quality gate: corrupted={'PASS' if result['corrupted_quality_success'] else 'FAIL'}, "
        f"repaired={'PASS' if result['repaired_quality_success'] else 'FAIL'}"
    )
    print(f"Report: {settings.paths.comparison_report}")
