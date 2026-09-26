from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import html
import re

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord

_TAG_RE = re.compile(r"<[^>]+>")

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "abs_url",
    "pdf_url",
    "comment",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "age_days",
    "text_for_embedding",
]


def clean_text(value) -> str:
    """Bo tag JATS/HTML, unescape entity va gop whitespace."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return normalize_whitespace(html.unescape(_TAG_RE.sub(" ", str(value))))


def _clean_list(values) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        item = clean_text(value)
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def build_text_for_embedding(row) -> str:
    """Ghep 5 phan: Title, Authors, Categories, Published, Summary."""
    return "\n".join(
        [
            f"Title: {row['title']}",
            f"Authors: {row['authors_joined']}",
            f"Categories: {row['categories_joined']}",
            f"Published: {row['published']}",
            f"Summary: {row['summary']}",
        ]
    )


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records thanh dataframe san sang de embed.

    - Normalize text (bo JATS tag, whitespace), authors, categories.
    - Parse published/updated, tinh `age_days = (run_date - published).days`.
    - Tao cot helper `authors_joined`, `categories_joined`, `summary_chars`, `text_for_embedding`.
    - Bo dong thieu paper_id/title/summary/published, khu trung lap theo `paper_id`.
    """
    df = pd.DataFrame([asdict(record) for record in records])
    if df.empty:
        return pd.DataFrame(columns=CLEAN_COLUMNS)

    for column in ["paper_id", "title", "summary", "primary_category", "abs_url", "pdf_url", "comment"]:
        df[column] = df[column].map(clean_text)
    df["paper_id"] = df["paper_id"].str.lower()
    df["authors"] = df["authors"].map(_clean_list)
    df["categories"] = df["categories"].map(_clean_list)
    df["primary_category"] = df.apply(
        lambda row: row["primary_category"] or (row["categories"][0] if row["categories"] else ""), axis=1
    )

    published = pd.to_datetime(df["published"], errors="coerce", utc=True)
    updated = pd.to_datetime(df["updated"], errors="coerce", utc=True).fillna(published)
    df["published"] = published.dt.strftime("%Y-%m-%d")
    df["updated"] = updated.dt.strftime("%Y-%m-%d")

    # Filter row xau: thieu truong bat buoc hoac khong parse duoc ngay
    valid = (df["paper_id"] != "") & (df["title"] != "") & (df["summary"] != "") & published.notna()
    df, published, updated = df[valid].copy(), published[valid], updated[valid]

    run_ts = pd.Timestamp(run_date if run_date.tzinfo else run_date.replace(tzinfo=UTC)).tz_convert("UTC")
    df["age_days"] = (run_ts.normalize() - published.dt.normalize()).dt.days.astype(int)

    df["authors_joined"] = df["authors"].map(compact_join)
    df["categories_joined"] = df["categories"].map(compact_join)
    df["summary_chars"] = df["summary"].str.len().astype(int)
    df["text_for_embedding"] = df.apply(build_text_for_embedding, axis=1)

    # Dedupe theo paper_id: giu ban updated moi nhat
    df["_updated_ts"] = updated
    df = df.sort_values(["paper_id", "_updated_ts"], ascending=[True, False])
    df = df.drop_duplicates(subset="paper_id", keep="first").drop(columns="_updated_ts")

    df = df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    return df[CLEAN_COLUMNS]
