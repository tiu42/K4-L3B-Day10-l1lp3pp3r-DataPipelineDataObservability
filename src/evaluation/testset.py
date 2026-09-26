from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json

TEST_SET_SIZE = 10
MIN_DOCUMENTS = TEST_SET_SIZE
# Phan bo 10 cau hoi deu qua 4 dang: 3 summary, 3 authors, 2 date, 2 categories
QUESTION_TYPES = ["summary", "authors", "date", "categories"]

# Mau cau hoi khop voi keyword trong `retrieval.qa._extract_answer`; title nam trong '...'
QUESTION_TEMPLATES = {
    "summary": "What is the summary of the paper '{title}'?",
    "authors": "Who authored the paper '{title}'?",
    "date": "When was the paper '{title}' published?",
    "categories": "What categories does the paper '{title}' belong to?",
}


def _ground_truth(row: pd.Series, question_type: str) -> str:
    if question_type == "summary":
        return first_sentence(row["summary"])
    if question_type == "authors":
        return row["authors_joined"]
    if question_type == "date":
        return str(row["published"])[:10]
    return row["categories_joined"]


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Tao bo evaluation set 10 cau hoi tu cleaned dataframe va ghi JSON vao `output_path`.

    Moi cau hoi dung mot paper khac nhau, chon trai deu tren corpus (sort theo paper_id
    de ket qua on dinh giua cac lan chay).
    """
    candidates = df.dropna(subset=["paper_id", "title", "summary", "published"])
    # Title chua dau nhay don se lam hong regex trich title trong qa.py
    candidates = candidates[~candidates["title"].str.contains("'", regex=False)]
    candidates = candidates.drop_duplicates(subset="paper_id").sort_values("paper_id").reset_index(drop=True)
    if len(candidates) < MIN_DOCUMENTS:
        raise ValueError(f"Need at least {MIN_DOCUMENTS} valid documents to build test set, got {len(candidates)}.")

    step = len(candidates) / TEST_SET_SIZE
    picked = [candidates.iloc[int(i * step)] for i in range(TEST_SET_SIZE)]

    test_set: list[dict[str, Any]] = []
    for i, row in enumerate(picked):
        question_type = QUESTION_TYPES[i % len(QUESTION_TYPES)]
        ground_truth = _ground_truth(row, question_type)
        if not ground_truth:
            question_type, ground_truth = "summary", _ground_truth(row, "summary")
        test_set.append(
            {
                "id": f"eval_{i + 1:03d}",
                "question_type": question_type,
                "question": QUESTION_TEMPLATES[question_type].format(title=row["title"]),
                "ground_truth": ground_truth,
                "ground_truth_doc_ids": [row["paper_id"]],
            }
        )

    write_json(output_path, test_set)
    return test_set
