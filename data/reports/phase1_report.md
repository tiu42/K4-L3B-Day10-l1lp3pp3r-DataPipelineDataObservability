# Phase 1 Baseline Report

## Source

| Field | Value |
|---|---|
| source_api | Crossref REST API |
| source_query | agentic retrieval augmented generation large language model |
| source_filter | from-pub-date:2026-03-30,has-abstract:true |
| source_mode | local snapshot |
| run_date | 2026-09-26T15:19:13+00:00 |
| raw_records | 24 |
| clean_rows | 24 |
| dropped_rows | 0 |
| test_questions | 10 |
| collection_name | papers-baseline |
| embedding_model | sentence-transformers/all-MiniLM-L6-v2 |

## Evaluation Metrics

| Metric | Value |
|---|---|
| samples | 10 |
| retrieval_hit_rate | 1.0000 |
| mean_token_f1 | 1.0000 |
| judge_accuracy | 1.0000 |
| mean_judge_score | 5 |
| ragas | {'skipped': 'Set RUN_RAGAS=1 to enable the slower Ragas pass.'} |

## Data Quality (Great Expectations) - PASS

Rows validated: 24

| Expectation | Column | Success | Observed | Unexpected |
|---|---|---|---|---|
| expect_table_row_count_to_be_between | - | True | 24 | - |
| expect_column_values_to_not_be_null | paper_id | True | - | 0 |
| expect_column_values_to_be_unique | paper_id | True | - | 0 |
| expect_column_values_to_not_be_null | title | True | - | 0 |
| expect_column_values_to_not_be_null | text_for_embedding | True | - | 0 |
| expect_column_value_lengths_to_be_between | summary | True | - | 0 |

## Freshness SLA

| Field | Value |
|---|---|
| generated_at | 2026-09-26T15:19:14.174334+00:00 |
| threshold_days | 180 |
| max_stale_ratio | 0.2500 |
| latest_published | 2026-07-22 |
| oldest_published | 2026-03-28 |
| stale_rows | 1 |
| total_rows | 24 |
| stale_ratio | 0.0417 |
| is_fresh | True |
