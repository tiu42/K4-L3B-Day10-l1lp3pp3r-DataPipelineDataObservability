from __future__ import annotations

from datetime import timedelta
import math
import random

import pandas as pd

from core.utils import now_utc, write_json
from ingestion.cleaning import build_text_for_embedding

SEED = 42
DROP_LATEST_FRACTION = 0.20
CORRUPT_FRACTION = 0.15  # ti le dong cho moi dang loi blank/noise/truncate/stale/duplicate
TRUNCATE_TITLE_CHARS = 7
STALE_SHIFT_DAYS = 365
NOISE_TOKENS = ["#@!%", "XJQZ", "0xDEADBEEF", "&&&", "lorem~ipsum", "NaN", "@@@"]


def _log(events: list[dict], corruption: str, paper_id: str, field: str | None, before, after) -> None:
    events.append(
        {"corruption": corruption, "paper_id": paper_id, "field": field, "before": before, "after": after}
    )


def _inject_noise(text: str, rng: random.Random) -> str:
    words = text.split()
    for _ in range(max(3, len(words) // 5)):
        words.insert(rng.randint(0, len(words)), rng.choice(NOISE_TOKENS))
    return " ".join(words)


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Gia lap 6 dang data corruption tren clean dataframe va ghi log vao `output_log_path`.

    1. Drop 20% records moi nhat.
    2. Blank summary.
    3. Inject noise vao summary.
    4. Truncate title < 8 ky tu.
    5. Lui published date 365 ngay.
    6. Duplicate rows.
    Moi dang loi (2-6) tac dong len mot nhom dong rieng biet, chon ngau nhien voi seed co dinh.
    Sau do rebuild `summary_chars` va `text_for_embedding`.
    """
    rng = random.Random(SEED)
    events: list[dict] = []
    input_rows = len(df)
    corrupted = df.copy().reset_index(drop=True)

    # 1. Drop latest records
    drop_count = math.ceil(input_rows * DROP_LATEST_FRACTION)
    latest_order = corrupted.sort_values(["published", "paper_id"], ascending=[False, True]).index
    dropped = latest_order[:drop_count]
    for idx in dropped:
        row = corrupted.loc[idx]
        _log(events, "drop_latest_records", row["paper_id"], None, row["published"], None)
    corrupted = corrupted.drop(index=dropped).reset_index(drop=True)

    # Chia cac dong con lai thanh nhom rieng cho tung dang loi
    group_size = max(1, int(input_rows * CORRUPT_FRACTION))
    order = list(corrupted.index)
    rng.shuffle(order)
    kinds = ["blank_summary", "inject_noise", "truncate_title", "stale_date", "duplicate_rows"]
    groups = {kind: order[i * group_size : (i + 1) * group_size] for i, kind in enumerate(kinds)}

    # 2. Blank summary
    for idx in groups["blank_summary"]:
        before = corrupted.at[idx, "summary"]
        corrupted.at[idx, "summary"] = ""
        _log(events, "blank_summary", corrupted.at[idx, "paper_id"], "summary", before, "")

    # 3. Inject noise
    for idx in groups["inject_noise"]:
        before = corrupted.at[idx, "summary"]
        after = _inject_noise(before, rng)
        corrupted.at[idx, "summary"] = after
        _log(events, "inject_noise", corrupted.at[idx, "paper_id"], "summary", before, after)

    # 4. Truncate title
    for idx in groups["truncate_title"]:
        before = corrupted.at[idx, "title"]
        after = before[:TRUNCATE_TITLE_CHARS]
        corrupted.at[idx, "title"] = after
        _log(events, "truncate_title", corrupted.at[idx, "paper_id"], "title", before, after)

    # 5. Stale date
    for idx in groups["stale_date"]:
        before = corrupted.at[idx, "published"]
        after = (pd.Timestamp(before) - timedelta(days=STALE_SHIFT_DAYS)).strftime("%Y-%m-%d")
        corrupted.at[idx, "published"] = after
        corrupted.at[idx, "age_days"] = int(corrupted.at[idx, "age_days"]) + STALE_SHIFT_DAYS
        _log(events, "stale_date", corrupted.at[idx, "paper_id"], "published", before, after)

    # Rebuild cot phu thuoc truoc khi nhan ban de ban sao giong het ban goc
    corrupted["summary_chars"] = corrupted["summary"].str.len().astype(int)
    corrupted["text_for_embedding"] = corrupted.apply(build_text_for_embedding, axis=1)

    # 6. Duplicate rows
    duplicates = corrupted.loc[groups["duplicate_rows"]]
    for paper_id in duplicates["paper_id"]:
        _log(events, "duplicate_rows", paper_id, None, None, "duplicated")
    corrupted = pd.concat([corrupted, duplicates], ignore_index=True)

    counts: dict[str, int] = {}
    for event in events:
        counts[event["corruption"]] = counts.get(event["corruption"], 0) + 1
    write_json(
        output_log_path,
        {
            "generated_at": now_utc().isoformat(),
            "seed": SEED,
            "input_rows": input_rows,
            "output_rows": len(corrupted),
            "counts": counts,
            "events": events,
        },
    )
    return corrupted
