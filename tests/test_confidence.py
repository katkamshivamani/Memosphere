"""Grounding rules: recorded / inferred / missing / conflicting, and guards."""

from __future__ import annotations

import pytest

from memory_agent.core.confidence import (
    EvidenceAssessor,
    EvidenceAssessment,
    Grounding,
)
from memory_agent.core.intent import Intent, IntentClassifier, IntentName
from memory_agent.models.memory import Record, RecordType
from memory_agent.models.suggestion import Suggestion, SuggestionType
from memory_agent.models.tool_result import ToolResult

ASSESSOR = EvidenceAssessor()
CLASSIFIER = IntentClassifier()


def _record(title: str, content: str, *, record_id: str = "mem_1", **metadata) -> Record:
    return Record(
        id=record_id,
        user_id="user_001",
        type=RecordType.MEMORY,
        title=title,
        content=content,
        source_module="memories",
        metadata=metadata,
    )


def _result(*records: Record, **data) -> ToolResult:
    return ToolResult(call_id="call_1", tool="search_memories", records=list(records), data=data)


def _intent(name: IntentName = IntentName.OBJECT_LOCATION, **kwargs) -> Intent:
    return Intent(name=name, needs_personal_data=True, **kwargs)


def _suggestion() -> Suggestion:
    return Suggestion(
        user_id="user_001",
        type=SuggestionType.SAVE_MEMORY,
        title="Wallet",
        description="Wallet is in the drawer.",
        payload={"title": "Wallet", "content": "Wallet is in the drawer."},
    )


# --------------------------------------------------------------------------- #
# Assessment
# --------------------------------------------------------------------------- #
def test_direct_match_is_recorded():
    intent = _intent()
    assessment = ASSESSOR.assess(
        query="Where is my wallet?",
        intent=intent,
        results=[_result(_record("Wallet location", "The wallet is in the study desk drawer."))],
    )
    assert assessment.grounding is Grounding.RECORDED
    assert assessment.direct_match is True
    assert assessment.sources[0].title == "Wallet location"
    assert "recorded information" in assessment.summary_for_user().lower()


def test_unrelated_records_are_inferred():
    assessment = ASSESSOR.assess(
        query="passport location",
        intent=_intent(),
        results=[_result(_record("Travel documents", "The blue folder holds important papers."))],
    )
    assert assessment.grounding is Grounding.INFERRED
    assert assessment.direct_match is False
    assert "inferred" in assessment.summary_for_user().lower()


def test_no_records_is_missing_and_not_proof_of_absence():
    assessment = ASSESSOR.assess(query="Did I take my pills?", intent=_intent(), results=[])
    assert assessment.grounding is Grounding.MISSING
    assert assessment.record_count == 0
    assert "couldn't find" in assessment.summary_for_user().lower()

    text = ASSESSOR.enforce(
        "Yes, you took your pills today.",
        assessment,
        _intent(IntentName.CONFIRMATION_QUESTION, is_medical=False),
    )
    assert "record" in text.lower()
    assert "didn't happen" in text.lower()


def test_duplicate_records_are_counted_once():
    record = _record("Wallet location", "Wallet is in the study desk drawer.")
    assessment = ASSESSOR.assess(
        query="Where is my wallet?",
        intent=_intent(),
        results=[_result(record), _result(record)],
    )
    assert assessment.record_count == 1


def test_conflict_metadata_makes_answer_conflicting():
    assessment = ASSESSOR.assess(
        query="Where is my wallet?",
        intent=_intent(),
        results=[
            _result(
                _record("Wallet location", "Wallet is in the study desk drawer."),
                _record(
                    "Wallet location",
                    "Wallet is in the kitchen drawer.",
                    record_id="mem_2",
                    conflict=True,
                ),
            )
        ],
    )
    assert assessment.grounding is Grounding.CONFLICTING
    assert assessment.conflicts
    assert "disagree" in assessment.summary_for_user().lower()


def test_conflicting_statuses_for_the_same_topic_are_detected():
    assessment = ASSESSOR.assess(
        query="Did the parcel arrive?",
        intent=_intent(IntentName.CONFIRMATION_QUESTION),
        results=[
            _result(
                _record("Parcel", "Parcel is due Tuesday.", record_id="m1", status="expected"),
                _record("Parcel", "Parcel arrived Monday.", record_id="m2", status="delivered"),
            )
        ],
    )
    assert assessment.grounding is Grounding.CONFLICTING


def test_suggestions_are_not_evidence_of_a_recorded_fact():
    suggestion_result = ToolResult(
        call_id="call_1", tool="suggest_memory_save", suggestion=_suggestion()
    )
    assessment = ASSESSOR.assess(
        query="Where is my wallet?", intent=_intent(), results=[suggestion_result]
    )
    assert assessment.grounding is Grounding.MISSING
    assert assessment.record_count == 0


# --------------------------------------------------------------------------- #
# Enforcement
# --------------------------------------------------------------------------- #
def test_inferred_answer_is_labelled():
    assessment = ASSESSOR.assess(
        query="passport location",
        intent=_intent(),
        results=[_result(_record("Travel documents", "The blue folder holds important papers."))],
    )
    text = ASSESSOR.enforce("It is probably in the blue folder.", assessment, _intent())
    assert text.lower().startswith("this is an inference")


def test_conflicting_answer_is_labelled():
    assessment = EvidenceAssessment(grounding=Grounding.CONFLICTING, conflicts=["Wallet location"])
    text = ASSESSOR.enforce("The wallet is in the study.", assessment, _intent())
    assert "records disagree" in text.lower()
    assert "wallet location" in text.lower()


def test_write_claim_without_a_suggestion_is_corrected():
    assessment = EvidenceAssessment(grounding=Grounding.RECORDED, record_count=1)
    text = ASSESSOR.enforce("I have saved your memory.", assessment, _intent())
    assert "can't change records directly" in text.lower()
    assert "nothing was saved or changed" in text.lower()


def test_write_claim_with_a_suggestion_points_to_approval():
    assessment = EvidenceAssessment(grounding=Grounding.RECORDED, record_count=1)
    text = ASSESSOR.enforce(
        "I have saved your memory.", assessment, _intent(), suggestions=[_suggestion()]
    )
    assert "prepared a suggestion" in text.lower()
    assert "nothing has been changed yet" in text.lower()


def test_medical_questions_get_a_disclaimer():
    intent = _intent(IntentName.CONFIRMATION_QUESTION, is_medical=True)
    assessment = EvidenceAssessment(grounding=Grounding.RECORDED, record_count=1)
    text = ASSESSOR.enforce("Yes, it is fine to take two.", assessment, intent)
    assert "not a medical professional" in text.lower()


def test_missing_answer_matches_the_intent():
    people = ASSESSOR.enforce(
        "", EvidenceAssessment(grounding=Grounding.MISSING), _intent(IntentName.PEOPLE_LOOKUP)
    )
    assert "saved person" in people.lower()
    activity = ASSESSOR.enforce(
        "", EvidenceAssessment(grounding=Grounding.MISSING), _intent(IntentName.ACTIVITY_HISTORY)
    )
    assert "did not happen" in activity.lower()


def test_sources_are_capped_at_eight():
    records = [
        _record(f"Wallet note {index}", "wallet drawer", record_id=f"mem_{index}")
        for index in range(12)
    ]
    assessment = ASSESSOR.assess(query="wallet", intent=_intent(), results=[_result(*records)])
    assert len(assessment.sources) == 8


def test_classifier_is_local_and_deterministic():
    first = CLASSIFIER.classify("Where did I keep my passport?")
    second = CLASSIFIER.classify("Where did I keep my passport?")
    assert first == second
    assert "memory" in first.categories


@pytest.mark.parametrize(
    "text,expected",
    [
        ("hello", IntentName.GREETING),
        ("What can you do?", IntentName.HELP),
        ("Where is my passport?", IntentName.OBJECT_LOCATION),
        ("Who is Sarah?", IntentName.PEOPLE_LOOKUP),
    ],
)
def test_classifier_recognizes_common_intents(text, expected):
    assert CLASSIFIER.classify(text).name is expected
