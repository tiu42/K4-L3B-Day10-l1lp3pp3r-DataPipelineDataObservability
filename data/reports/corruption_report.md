# Corruption & Repair Report

## Evaluation Metrics: Baseline vs Corrupted vs Repaired

| Metric | Baseline | Corrupted | Repaired |
|---|---|---|---|
| samples | 10 | 10 | 10 |
| retrieval_hit_rate | 1.0000 | 0.9000 | 1.0000 |
| mean_token_f1 | 1.0000 | 0.6914 | 1.0000 |
| judge_accuracy | 1.0000 | 0.7000 | 1.0000 |
| mean_judge_score | 5 | 3.6000 | 5 |

## Impact Analysis

- **retrieval_hit_rate**: 1.0000 -> 0.9000 (drop 0.1000) -> 1.0000, recovery 100%.
- **mean_token_f1**: 1.0000 -> 0.6914 (drop 0.3086) -> 1.0000, recovery 100%.
- **judge_accuracy**: 1.0000 -> 0.7000 (drop 0.3000) -> 1.0000, recovery 100%.
- **mean_judge_score**: 5.0000 -> 3.6000 (drop 1.4000) -> 5.0000, recovery 100%.

## Data Quality (Great Expectations)

| Expectation | Column | Corrupted | Repaired |
|---|---|---|---|
| expect_table_row_count_to_be_between | - | PASS | PASS |
| expect_column_values_to_not_be_null | paper_id | PASS | PASS |
| expect_column_values_to_be_unique | paper_id | FAIL (6 unexpected) | PASS |
| expect_column_values_to_not_be_null | title | PASS | PASS |
| expect_column_values_to_not_be_null | text_for_embedding | PASS | PASS |
| expect_column_value_lengths_to_be_between | summary | FAIL (3 unexpected) | PASS |
| **overall** | - | FAIL | PASS |

## Freshness SLA

| Field | Corrupted | Repaired |
|---|---|---|
| latest_published | 2026-06-12 | 2026-07-22 |
| oldest_published | 2025-04-30 | 2026-03-28 |
| stale_rows | 5 | 1 |
| total_rows | 22 | 24 |
| stale_ratio | 0.2273 | 0.0417 |
| is_fresh | True | True |

## Conclusion

- Silent failure: the corrupted dataset was indexed and served without any runtime error; only the quality gate and the evaluation metrics exposed the damage.
- Repair rebuilt the dataset idempotently from the immutable raw snapshot; the repaired quality gate passed.
