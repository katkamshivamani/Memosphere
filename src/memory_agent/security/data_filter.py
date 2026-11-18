"""Redaction, secret detection and prompt-injection screening.

Two different trust problems are handled here:

1. **Secret leakage** - credentials must never reach logs, chat history,
   settings files or a cloud provider.
2. **Untrusted retrieved content** - memories are *data*.  Text stored in a
   memory may contain instructions; those instructions must never be treated as
   system instructions or grant capabilities.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

# --------------------------------------------------------------------------- #
# Secret detection / redaction
# --------------------------------------------------------------------------- #
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9\-_]{16,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{16,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-._~+/]{12,}=*")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("password_assignment", re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*\S+")),
)

_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "api-key",
        "password",
        "passwd",
        "secret",
        "client_secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "auth_token",
        "private_key",
        "session_token",
        "credential",
        "credentials",
    }
)

REDACTED = "[redacted]"


@dataclass(frozen=True)
class SecretFinding:
    kind: str
    preview: str  # masked, never the full value
    start: int
    end: int


def _mask(value: str) -> str:
    value = value.strip()
    if len(value) <= 8:
        return REDACTED
    return f"{value[:3]}…{value[-2:]}"


def find_secrets(text: str) -> list[SecretFinding]:
    """Return masked findings for anything that looks like a credential."""
    if not isinstance(text, str) or not text:
        return []
    findings: list[SecretFinding] = []
    for kind, pattern in _SECRET_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                SecretFinding(kind=kind, preview=_mask(match.group(0)), start=match.start(), end=match.end())
            )
    return findings


def contains_secret(text: str) -> bool:
    return bool(find_secrets(text))


def redact_text(text: str) -> str:
    """Replace credential-looking substrings with ``[redacted]``."""
    if not isinstance(text, str) or not text:
        return text
    result = text
    for _kind, pattern in _SECRET_PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def redact_value(value: Any, _depth: int = 0) -> Any:
    """Recursively redact secrets in dicts/lists, preserving shape for logs."""
    if _depth > 8:
        return "[depth-limit]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _SENSITIVE_KEYS:
                cleaned[key] = REDACTED
            else:
                cleaned[str(key)] = redact_value(item, _depth + 1)
        return cleaned
    if isinstance(value, (list, tuple, set)):
        return [redact_value(item, _depth + 1) for item in value]
    return value


def redact_for_log(event: str, data: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Build a log record with all sensitive values redacted."""
    return {"event": event, "data": redact_value(dict(data or {}))}


_ERROR_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\s'\"]+|/(?:home|Users|var|tmp)/[^\s'\"]+")
_ERROR_KEY_PATTERN = re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b|\bsk-[A-Za-z0-9\-_]{16,}\b")


def sanitize_user_error(message: str) -> str:
    """Strip paths, keys and stack frames from an error before display."""
    text = _ERROR_KEY_PATTERN.sub(REDACTED, message or "")
    text = _ERROR_PATH_PATTERN.sub("[path]", text)
    text = re.sub(r"Traceback \(most recent call last\):.*", "An internal error occurred.", text, flags=re.S)
    return text.strip()


# --------------------------------------------------------------------------- #
# Untrusted content / prompt injection
# --------------------------------------------------------------------------- #
class PromptInjectionDetector:
    """Heuristic detector for instruction-like text inside retrieved records.

    Detection is advisory and auditable; enforcement does not rely on it.
    Permission checks, argument schemas and the approval gate are what actually
    prevent misuse.
    """

    PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("ignore_instructions", re.compile(
            r"(?i)\b(ignore|disregard|forget)\b[^.\n]{0,40}\b(previous|prior|above|system)\b"
            r"[^.\n]{0,20}\b(instructions?|prompts?|rules?)\b")),
        ("role_override", re.compile(r"(?i)\byou are (now|no longer)\b|\bact as\b|\bpretend to be\b")),
        ("system_prompt_exfiltration", re.compile(
            r"(?i)\b(reveal|show|print|repeat|leak)\b[^.\n]{0,30}\b(system prompt|instructions|api key|token)\b")),
        ("tool_coercion", re.compile(
            r"(?i)\b(call|invoke|execute|run)\b[^.\n]{0,30}\b(tool|function|command|sql)\b")),
        ("data_exfiltration", re.compile(
            r"(?i)\b(send|email|upload|post|share)\b[^.\n]{0,40}\b(all|every|other users?)\b"
            r"[^.\n]{0,20}\b(memor(y|ies)|records?|data)\b")),
        ("permission_bypass", re.compile(
            r"(?i)\b(bypass|disable|skip)\b[^.\n]{0,30}\b(permissions?|security|authentication|checks?)\b")),
        ("destructive", re.compile(r"(?i)\b(delete|drop|truncate|erase)\b[^.\n]{0,30}\b(table|database|memories)\b")),
    )

    def scan(self, text: str) -> list[str]:
        if not isinstance(text, str) or not text.strip():
            return []
        found: list[str] = []
        for name, pattern in self.PATTERNS:
            if pattern.search(text):
                found.append(name)
        return found

    def is_suspicious(self, text: str) -> bool:
        return bool(self.scan(text))


def wrap_untrusted(record_id: str, body: str, *, flagged: bool = False) -> str:
    """Delimit untrusted record content for the model prompt."""
    marker = ' data-flagged="suspicious-instructions"' if flagged else ""
    safe_body = body.replace("</untrusted_record>", "&lt;/untrusted_record&gt;")
    return f'<untrusted_record id="{record_id}"{marker}>\n{safe_body}\n</untrusted_record>'


@dataclass
class InjectionReport:
    """Aggregated screening results for one context build."""

    flagged_record_ids: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        return bool(self.flagged_record_ids)

    def as_dict(self) -> dict[str, Any]:
        return {
            "flagged_record_ids": list(self.flagged_record_ids),
            "categories": list(self.categories),
        }
