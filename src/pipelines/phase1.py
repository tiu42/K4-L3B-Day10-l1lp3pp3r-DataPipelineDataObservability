from __future__ import annotations

import logging
import os
from typing import Any

from core.config import Settings, load_settings
from core.utils import read_json, write_csv, write_json, now_utc
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex

logger = logging.getLogger(__name__)

DEMO_QUESTIONS = [
    "Which papers discuss agentic retrieval-augmented generation?",
    "How can data quality gates protect a production RAG system?",
]


def _run_agent_demo(settings: Settings, index: LocalEmbeddingIndex) -> None:
    """Demo agent tren vai cau hoi (bat bang RUN_AGENT_DEMO=1, ton LLM call)."""
    from retrieval.agent import build_agent, run_agent_question

    try:
        agent = build_agent(settings, index)
        answers = [{"question": q, "answer": run_agent_question(agent, q)} for q in DEMO_QUESTIONS]
    except Exception as exc:  # demo khong duoc lam fail pipeline
        answers = [{"error": f"Agent demo failed: {exc}"}]
    write_json(settings.paths.demo_answers, answers)


def run_phase1_pipeline(settings: Settings) -> dict[str, Any]:
    """Baseline pipeline: Ingest -> Clean -> Quality gate -> Index -> Testset -> Evaluate -> Report."""
    paths = settings.paths
    run_date = now_utc()

    # 1. Ingest (API live hoac fallback snapshot)
    records = fetch_source_records(settings)
    logger.info("Ingested %d raw records", len(records))

    # 2. Clean + luu artifact
    df = build_clean_dataframe(records, run_date)
    write_csv(df, paths.clean_csv)
    df.to_json(paths.clean_json, orient="records", indent=2, force_ascii=False)
    logger.info("Cleaned %d rows -> %s", len(df), paths.clean_csv)

    # 3. Quality gate (GX 1.x) + freshness: chan data xau truoc khi vao vector DB
    quality = run_data_quality_checks(df, settings, "baseline")
    freshness = build_freshness_report(df, settings, paths.freshness_report)
    if not quality["success"]:
        failed = [f"{c['expectation']}({c['column']})" for c in quality["failed_expectations"]]
        raise RuntimeError(f"Data quality gate failed, refusing to index: {failed}")

    # 4. Index ChromaDB
    index = LocalEmbeddingIndex.build(df, settings, paths.embeddings_json)

    # 5. Test set (tai su dung neu da co, tru khi REFRESH_TEST_SET=1)
    if settings.refresh_test_set or not paths.eval_testset.exists():
        test_set = build_test_set(df, paths.eval_testset)
    else:
        test_set = read_json(paths.eval_testset)

    # 6. Evaluate baseline
    bundle = evaluate_pipeline(settings, index, paths.eval_testset, paths.baseline_metrics, paths.baseline_answers)

    source_summary = {
        "source_api": settings.source_api,
        "source_query": settings.source_query,
        "source_filter": settings.source_filter,
        "source_mode": "live API (REFRESH_SOURCE=1)" if settings.refresh_source else "local snapshot",
        "run_date": run_date.isoformat(timespec="seconds"),
        "raw_records": len(records),
        "clean_rows": int(len(df)),
        "dropped_rows": len(records) - int(len(df)),
        "test_questions": len(test_set),
        "collection_name": index.collection_name,
        "embedding_model": settings.embedding_model,
    }
    generate_phase1_report(paths.baseline_report, source_summary, bundle.summary, quality, freshness)

    if os.getenv("RUN_AGENT_DEMO", "").lower() in {"1", "true", "yes"}:
        _run_agent_demo(settings, index)

    return {
        "source": source_summary,
        "metrics": bundle.summary,
        "quality_success": quality["success"],
        "freshness": freshness,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    result = run_phase1_pipeline(load_settings())
    metrics = result["metrics"]
    print(
        f"Phase 1 done: {result['source']['clean_rows']} clean rows, "
        f"hit_rate={metrics['retrieval_hit_rate']:.2f}, token_f1={metrics['mean_token_f1']:.3f}, "
        f"quality={result['quality_success']}, is_fresh={result['freshness']['is_fresh']}"
    )
