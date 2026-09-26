from __future__ import annotations

from pathlib import Path
from typing import Any

from core.utils import write_text


def _md(value: Any) -> str:
    if value is None:
        return "-"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _fmt(value: Any) -> str:
    return f"{value:.4f}" if isinstance(value, float) else _md(value)


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Viet markdown report cho baseline phase: source, metrics, quality, freshness."""
    lines = ["# Phase 1 Baseline Report", "", "## Source", "", "| Field | Value |", "|---|---|"]
    lines += [f"| {key} | {_md(value)} |" for key, value in source_summary.items()]

    lines += ["", "## Evaluation Metrics", "", "| Metric | Value |", "|---|---|"]
    lines += [f"| {key} | {_fmt(value)} |" for key, value in metrics.items() if key != "ragas"]
    if "ragas" in metrics:
        lines.append(f"| ragas | {_md(metrics['ragas'])} |")

    status = "PASS" if quality.get("success") else "FAIL"
    lines += [
        "",
        f"## Data Quality (Great Expectations) - {status}",
        "",
        f"Rows validated: {quality.get('row_count')}",
        "",
        "| Expectation | Column | Success | Observed | Unexpected |",
        "|---|---|---|---|---|",
    ]
    for check in quality.get("checks", []):
        lines.append(
            f"| {check['expectation']} | {check.get('column') or '-'} | {check['success']} "
            f"| {_md(check.get('observed_value'))} | {_md(check.get('unexpected_count'))} |"
        )

    lines += ["", "## Freshness SLA", "", "| Field | Value |", "|---|---|"]
    lines += [f"| {key} | {_fmt(value)} |" for key, value in freshness.items()]
    if not freshness.get("is_fresh", True):
        lines += ["", "> WARNING: stale ratio exceeds the freshness SLA, refresh the source data."]

    write_text(Path(report_path), "\n".join(lines) + "\n")


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Viet markdown report so sanh baseline/corrupted/repaired."""
    lines = [
        "# Corruption & Repair Report",
        "",
        "## Evaluation Metrics: Baseline vs Corrupted vs Repaired",
        "",
        format_metrics_comparison(baseline_metrics, corrupted_metrics, repaired_metrics),
        "",
        "## Impact Analysis",
        "",
    ]
    for metric in COMPARISON_METRICS:
        base, bad, fixed = (m.get(metric) for m in (baseline_metrics, corrupted_metrics, repaired_metrics))
        if not all(isinstance(v, (int, float)) for v in (base, bad, fixed)):
            continue
        drop = base - bad
        recovery = f"{(fixed - bad) / drop:.0%}" if drop > 0 else "n/a (no degradation)"
        lines.append(f"- **{metric}**: {base:.4f} -> {bad:.4f} (drop {drop:.4f}) -> {fixed:.4f}, recovery {recovery}.")

    lines += [
        "",
        "## Data Quality (Great Expectations)",
        "",
        "| Expectation | Column | Corrupted | Repaired |",
        "|---|---|---|---|",
    ]
    repaired_checks = {(c["expectation"], c.get("column")): c for c in repaired_quality.get("checks", [])}
    for check in corrupted_quality.get("checks", []):
        repaired = repaired_checks.get((check["expectation"], check.get("column")), {})
        lines.append(
            f"| {check['expectation']} | {check.get('column') or '-'} "
            f"| {_check_status(check)} | {_check_status(repaired)} |"
        )
    lines += [
        f"| **overall** | - | {_status(corrupted_quality.get('success'))} | {_status(repaired_quality.get('success'))} |",
        "",
        "## Freshness SLA",
        "",
        "| Field | Corrupted | Repaired |",
        "|---|---|---|",
    ]
    for key in ["latest_published", "oldest_published", "stale_rows", "total_rows", "stale_ratio", "is_fresh"]:
        lines.append(f"| {key} | {_fmt(corrupted_freshness.get(key))} | {_fmt(repaired_freshness.get(key))} |")

    lines += ["", "## Conclusion", ""]
    if not corrupted_quality.get("success"):
        lines.append(
            "- Silent failure: the corrupted dataset was indexed and served without any runtime error; "
            "only the quality gate and the evaluation metrics exposed the damage."
        )
    lines.append(
        "- Repair rebuilt the dataset idempotently from the immutable raw snapshot; "
        f"the repaired quality gate {'passed' if repaired_quality.get('success') else 'failed'}."
    )
    write_text(Path(report_path), "\n".join(lines) + "\n")


COMPARISON_METRICS = ["retrieval_hit_rate", "mean_token_f1", "judge_accuracy", "mean_judge_score"]


def _status(success: Any) -> str:
    return "PASS" if success else "FAIL"


def _check_status(check: dict[str, Any]) -> str:
    if not check:
        return "-"
    unexpected = check.get("unexpected_count")
    return f"{_status(check.get('success'))} ({unexpected} unexpected)" if unexpected else _status(check.get("success"))


def format_metrics_comparison(
    baseline_metrics: dict[str, Any], corrupted_metrics: dict[str, Any], repaired_metrics: dict[str, Any]
) -> str:
    """Bang markdown 3 cot Baseline | Corrupted | Repaired (dung cho report va console)."""
    lines = ["| Metric | Baseline | Corrupted | Repaired |", "|---|---|---|---|"]
    for metric in ["samples", *COMPARISON_METRICS]:
        values = [_fmt(m.get(metric)) for m in (baseline_metrics, corrupted_metrics, repaired_metrics)]
        lines.append(f"| {metric} | {' | '.join(values)} |")
    return "\n".join(lines)
