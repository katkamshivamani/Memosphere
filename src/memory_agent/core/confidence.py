"""Evidence assessment and grounded-response enforcement.

This module is the guardrail behind the promise "no fabricated memories".  It
works on *retrieved records only* and uses deterministic, documented rules -
never invented confidence percentages.

Grounding states
----------------
``RECORDED``
    At least one retrieved record directly matches the question's content words.
``INFERRED``
    Records were retrieved but only relate indirectly; the answer must be
    presented as an inference.
``CONFLICTING``
    Retrieved records disagree (explicit conflict metadata, contradictory
    statuses for the same topic, or conflicts reported by the service).
``MISSING``
    No recorded information was retrieved.  A missing record is *not* proof
    that an event did not happen.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Iterable, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from memory_agent.core.intent import Intent, IntentName
from memory_agent.models.memory import Record, SourceRef
from memory_agent.models.suggestion import Suggestion
from memory_agent.models.tool_result import ToolResult


class Grounding(str, Enum):
    RECORDED = "recorded"
    INFERRED = "inferred"
    MISSING = "missing"
    CONFLICTING = "conflicting"

    @property
    def label(self) -> str:
        return {
            Grounding.RECORDED: "Recorded information",
            Grounding.INFERRED: "Inferred from related records",
            Grounding.MISSING: "No recorded information",
            Grounding.CONFLICTING: "Records conflict",
        }[self]


class EvidenceAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grounding: Grounding
    record_count: int = 0
    sources: list[SourceRef] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    direct_match: bool = False
    notes: str = ""

    def summary_for_user(self) -> str:
        if self.grounding is Grounding.MISSING:
            return "I couldn't find a recorded source for this."
        if self.grounding is Grounding.CONFLICTING:
            return "Your records disagree; both versions are shown."
        label = self.grounding.label
        return f"{label} · {self.record_count} record{'s' if self.record_count != 1 else ''}"


_STOPWORDS = {
    "the", "and", "for", "was", "were", "did", "does", "what", "where", "when",
    "who", "why", "how", "you", "your", "yours", "have", "has", "had", "with",
    "about", "that", "this", "today", "yesterday", "tomorrow", "please", "tell",
    "remember", "memory", "memories", "my", "mine", "our", "ours", "from", "into",
    "did", "done", "can", "could", "would", "should", "any", "all", "are", "is",
}

_TOKEN = re.compile(r"[a-z0-9']+")

_HEDGE_PATTERNS = re.compile(
    r"(?i)\b(can(?:no|')?t confirm|cannot confirm|could(?: no|n')?t find|could not find|"
    r"no record|not recorded|nothing recorded|don't have|do not have|didn't find|"
    r"did not find|unable to find|i don't know|not in your (?:saved )?(?:records|memories)|"
    r"no saved (?:record|memory|information)|not enough information)\b"
)

_ASSERTION_PATTERNS = re.compile(
    r"(?i)(^|\n)\s*(yes\b|you (?:did|took|ate|went|visited|left|kept|placed|stored|have)\b|"
    r"it (?:is|was) (?:in|on|at)\b|there is a record (?:that|of)\b)"
)

_WRITE_CLAIMS = re.compile(
    r"(?i)\b(i (?:have )?(?:saved|created|added|updated|changed|set|stored|deleted)|"
    r"i've (?:saved|created|added|updated|changed|set|stored|deleted)|"
    r"your (?:memory|reminder) (?:has been|was) (?:saved|created|updated|added))\b"
)


class EvidenceAssessor:
    """Compute grounding from tool results and enforce it on the final answer."""

    # -- assessment ------------------------------------------------------ #
    @staticmethod
    def _content_tokens(text: str) -> set[str]:
        return {
            token for token in _TOKEN.findall((text or "").lower())
            if len(token) > 2 and token not in _STOPWORDS
        }

    def assess(
        self,
        *,
        query: str,
        intent: Intent,
        results: Sequence[ToolResult],
        extra_conflicts: Optional[Iterable[str]] = None,
    ) -> EvidenceAssessment:
        read_records: list[Record] = []
        conflicts: list[str] = [c for c in (extra_conflicts or []) if c]
        for result in results:
            if not result.ok:
                continue
            # Suggestion-only results never count as evidence of a recorded fact.
            if result.suggestion is not None and not result.records:
                continue
            read_records.extend(result.records)
            data_conflicts = result.data.get("conflicts") if isinstance(result.data, dict) else None
            if isinstance(data_conflicts, list):
                conflicts.extend(str(item) for item in data_conflicts if item)

        # Deduplicate by (type, id) while preserving order.
        seen: set[tuple[str, str]] = set()
        unique_records: list[Record] = []
        for record in read_records:
            key = (record.type.value, record.id)
            if key in seen:
                continue
            seen.add(key)
            unique_records.append(record)

        conflicts.extend(self._detect_conflicts(unique_records))

        if not unique_records:
            return EvidenceAssessment(
                grounding=Grounding.MISSING,
                record_count=0,
                categories=[],
                conflicts=conflicts,
                notes="No authorized records were found for this question.",
            )

        query_tokens = self._content_tokens(query)
        direct = False
        for record in unique_records:
            record_tokens = self._content_tokens(f"{record.title} {record.content}")
            if not query_tokens:
                direct = True
                break
            overlap = query_tokens & record_tokens
            # Direct when at least half of the meaningful query words appear, or
            # when the record title itself matches a query word.
            if len(overlap) >= max(1, (len(query_tokens) + 1) // 2) or (
                query_tokens & self._content_tokens(record.title)
            ):
                direct = True
                break

        sources = [record.source_ref() for record in unique_records[:8]]
        categories = sorted({record.type.value for record in unique_records})
        grounding = Grounding.MISSING
        if conflicts:
            grounding = Grounding.CONFLICTING
        elif direct:
            grounding = Grounding.RECORDED
        elif unique_records:
            grounding = Grounding.INFERRED

        return EvidenceAssessment(
            grounding=grounding,
            record_count=len(unique_records),
            sources=sources,
            categories=categories,
            conflicts=list(dict.fromkeys(conflicts)),
            direct_match=direct,
        )

    @staticmethod
    def _detect_conflicts(records: Sequence[Record]) -> list[str]:
        conflicts: list[str] = []
        groups: dict[tuple[str, str], list[Record]] = {}
        for record in records:
            metadata = record.metadata or {}
            if metadata.get("conflict") or metadata.get("conflict_with"):
                conflicts.append(record.title or record.id)
            key = (record.type.value, (record.title or "").strip().casefold())
            groups.setdefault(key, []).append(record)
        for (record_type, title), group in groups.items():
            statuses = {str((r.metadata or {}).get("status", "")).casefold() for r in group}
            statuses.discard("")
            if len(statuses) > 1:
                conflicts.append(f"{title or record_type}: {' / '.join(sorted(statuses))}")
        return list(dict.fromkeys(conflicts))

    # -- enforcement ----------------------------------------------------- #
    def enforce(
        self,
        text: str,
        assessment: EvidenceAssessment,
        intent: Intent,
        *,
        suggestions: Sequence[Suggestion] = (),
    ) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            cleaned = self._missing_answer(intent)

        if assessment.grounding is Grounding.MISSING and not suggestions:
            # With no authorized evidence, any personal claim in the model text is
            # unsupported. It is discarded rather than merely prefixed with a
            # disclaimer, so a fabricated location or event never reaches the user.
            if intent.needs_personal_data or _ASSERTION_PATTERNS.search(cleaned):
                cleaned = self._missing_answer(intent)
        elif assessment.grounding is Grounding.CONFLICTING:
            if not re.search(r"(?i)\b(conflict|disagree|differ|different versions|inconsistent)\b", cleaned):
                conflict_list = "; ".join(assessment.conflicts[:3]) or "the records"
                cleaned = (
                    f"Your records disagree about this ({conflict_list}).\n\n{cleaned}"
                )
        elif assessment.grounding is Grounding.INFERRED:
            if not re.search(r"(?i)\b(infer|inference|related records|based on|suggest)\b", cleaned):
                cleaned = (
                    "This is an inference from related records, not a direct record:\n\n" + cleaned
                )

        if intent.is_medical:
            if not re.search(r"(?i)\b(not a medical professional|medical advice|speak (?:with|to) (?:a|your) (?:doctor|pharmacist))\b", cleaned):
                cleaned += (
                    "\n\nI'm a memory assistant, not a medical professional, so I can't "
                    "give medical advice. For medication decisions, please check with your "
                    "doctor or pharmacist."
                )

        if suggestions:
            cleaned = self._guard_write_claims(cleaned)
            cleaned += (
                "\n\nI've prepared a suggestion below. Nothing has been changed yet - "
                "please review and approve it first."
            )
        elif _WRITE_CLAIMS.search(cleaned):
            cleaned = _WRITE_CLAIMS.sub("I can't change records directly", cleaned)
            cleaned += "\n\nNothing was saved or changed."

        return cleaned.strip()

    @staticmethod
    def _guard_write_claims(text: str) -> str:
        return _WRITE_CLAIMS.sub("I've prepared a suggestion", text)

    @staticmethod
    def _missing_answer(intent: Intent) -> str:
        if intent.name is IntentName.CONFIRMATION_QUESTION:
            if intent.is_medical:
                return (
                    "I can't confirm that from your recorded activities. There is no "
                    "record of it today, but a missing record doesn't prove it didn't happen."
                )
            return (
                "I couldn't find a record confirming that. Nothing is recorded, but a "
                "missing record doesn't prove it didn't happen."
            )
        if intent.name is IntentName.OBJECT_LOCATION:
            return (
                "I couldn't find where that is in your saved memories. It may not have "
                "been written down."
            )
        if intent.name is IntentName.PEOPLE_LOOKUP:
            return "I couldn't find a saved person matching that."
        if intent.name is IntentName.PLACE_LOOKUP:
            return "I couldn't find a saved place matching that."
        if intent.name is IntentName.REMINDER_LOOKUP:
            return "I couldn't find any upcoming reminders in that period."
        if intent.name is IntentName.ROUTINE_LOOKUP:
            return "I couldn't find a saved routine matching that."
        if intent.name is IntentName.ACTIVITY_HISTORY:
            return (
                "I couldn't find any recorded activities matching that. Missing records "
                "don't prove that something did not happen."
            )
        return "I couldn't find any recorded information about that. It may not have been written down."
