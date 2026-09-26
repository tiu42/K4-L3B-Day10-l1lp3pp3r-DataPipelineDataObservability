from __future__ import annotations

from dataclasses import asdict, dataclass
import html
import logging
from pathlib import Path
import re
import time

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json

logger = logging.getLogger(__name__)

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4
REQUEST_TIMEOUT_SECONDS = 30
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _clean_text(value: str | None) -> str:
    """Bo tag JATS/HTML, unescape entity va gop whitespace."""
    if not value:
        return ""
    return normalize_whitespace(html.unescape(_TAG_RE.sub(" ", value)))


def _first(values: list | None) -> str:
    return _clean_text(values[0]) if values else ""


def _format_date(date_field: dict | None) -> str:
    """Crossref date -> 'YYYY-MM-DD' (thieu thang/ngay thi mac dinh 01)."""
    if not date_field:
        return ""
    parts = (date_field.get("date-parts") or [[]])[0]
    if parts and parts[0]:
        year, month, day = (list(parts) + [1, 1])[:3]
        return f"{int(year):04d}-{int(month or 1):02d}-{int(day or 1):02d}"
    date_time = date_field.get("date-time")
    return date_time[:10] if date_time else ""


def _parse_authors(raw_authors: list | None) -> list[str]:
    authors: list[str] = []
    for author in raw_authors or []:
        name = _clean_text(" ".join(filter(None, [author.get("given"), author.get("family")])))
        name = name or _clean_text(author.get("name"))
        if name and name not in authors:
            authors.append(name)
    return authors


def _pdf_url(item: dict, fallback: str) -> str:
    for link in item.get("link") or []:
        if link.get("content-type") == "application/pdf" and link.get("URL"):
            return link["URL"]
    return fallback


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref `/works` payload thanh list PaperRecord.

    Bo qua record khong co DOI, title hoac abstract; dedupe theo DOI.
    """
    items = (payload.get("message") or {}).get("items") or []
    records: list[PaperRecord] = []
    seen: set[str] = set()

    for item in items:
        doi = normalize_whitespace(item.get("DOI") or "").lower()
        title = _first(item.get("title"))
        summary = _clean_text(item.get("abstract"))
        if not doi or not title or not summary or doi in seen:
            continue
        seen.add(doi)

        categories = [_clean_text(s) for s in item.get("subject") or [] if _clean_text(s)]
        if not categories:
            categories = [_clean_text(c) for c in item.get("container-title") or [] if _clean_text(c)]

        published = (
            _format_date(item.get("published"))
            or _format_date(item.get("published-print"))
            or _format_date(item.get("published-online"))
            or _format_date(item.get("issued"))
            or _format_date(item.get("created"))
        )
        updated = _format_date(item.get("updated")) or published
        abs_url = item.get("URL") or f"https://doi.org/{doi}"

        records.append(
            PaperRecord(
                paper_id=doi,
                title=title,
                summary=summary,
                authors=_parse_authors(item.get("author")),
                categories=categories,
                primary_category=categories[0] if categories else "",
                published=published,
                updated=updated,
                abs_url=abs_url,
                pdf_url=_pdf_url(item, abs_url),
                comment=f"Crossref record {doi}",
            )
        )
    return records


def _request_crossref(params: dict) -> dict:
    """GET Crossref voi retry + exponential backoff cho 429/5xx va loi mang."""
    headers = {"User-Agent": "day10-data-observability-lab/0.1 (mailto:student@example.com)"}
    last_error: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.get(
                CROSSREF_WORKS_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS
            )
            if response.status_code in RETRYABLE_STATUS_CODES:
                raise requests.HTTPError(f"Retryable status {response.status_code}", response=response)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and status not in RETRYABLE_STATUS_CODES:
                raise
            last_error = exc
            if attempt == MAX_ATTEMPTS:
                break
            retry_after = exc.response.headers.get("Retry-After") if exc.response is not None else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 ** attempt
            logger.warning("Crossref request failed (%s), retry %d/%d in %.0fs", exc, attempt, MAX_ATTEMPTS, delay)
            time.sleep(delay)

    raise RuntimeError(f"Crossref API unavailable after {MAX_ATTEMPTS} attempts: {last_error}")


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Goi Crossref API (hoac fallback snapshot local), luu raw response + records.

    - `REFRESH_SOURCE=1` hoac chua co snapshot: goi API live, ghi de raw response.
    - Nguoc lai, hoac khi API loi (mat mang, 429/503 sau retry): doc snapshot
      `settings.paths.raw_api_response` de pipeline van chay duoc offline.
    """
    raw_path = settings.paths.raw_api_response
    payload: dict | None = None

    if settings.refresh_source or not raw_path.exists():
        params = {
            "query": settings.source_query,
            "filter": settings.source_filter,
            "rows": settings.max_results,
        }
        try:
            payload = _request_crossref(params)
            write_json(raw_path, payload)
            logger.info("Fetched Crossref payload live -> %s", raw_path)
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            if not raw_path.exists():
                raise RuntimeError(f"Crossref fetch failed and no local snapshot at {raw_path}") from exc
            logger.warning("Crossref fetch failed (%s); falling back to snapshot %s", exc, raw_path)

    if payload is None:
        payload = read_json(raw_path)
        logger.info("Loaded Crossref snapshot from %s", raw_path)

    records = parse_crossref_payload(payload)
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc JSON snapshot (list dict) va map thanh `PaperRecord`."""
    return [PaperRecord(**row) for row in read_json(path)]
