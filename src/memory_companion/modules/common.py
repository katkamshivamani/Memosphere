"""Shared helpers for the host application's data services."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

_TOKEN = re.compile(r"[A-Za-z0-9]+")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def to_iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def parse_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def search_tokens(query: str, limit: int = 6) -> list[str]:
    tokens = [token for token in _TOKEN.findall(query or "") if len(token) > 2]
    # Stable de-duplication, longest first (more specific terms first).
    seen: list[str] = []
    for token in sorted(tokens, key=len, reverse=True):
        lowered = token.lower()
        if lowered not in seen:
            seen.append(lowered)
        if len(seen) >= limit:
            break
    return seen


def like_clause(columns: tuple[str, ...], tokens: list[str]) -> tuple[str, list[Any]]:
    """Build an OR-of-LIKE clause across columns for the supplied tokens."""
    if not tokens:
        return "", []
    per_token = " OR ".join(f"{column} LIKE ?" for column in columns)
    clause = "(" + " OR ".join(f"({per_token})" for _ in tokens) + ")"
    params: list[Any] = []
    for token in tokens:
        pattern = f"%{token}%"
        params.extend([pattern] * len(columns))
    return clause, params


def row_to_dict(row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
