"""Bounded agent orchestration loop.

Guarantees enforced here (not only by prompt text):

* a maximum of five tool rounds per user request (configurable, hard-capped);
* cancellation checks between every step;
* provider retries only for transient failures;
* per-call argument validation, permission checks, timeouts and duplicate
  protection (delegated to the registry);
* every failure is mapped to a safe, structured error;
* the final answer is screened for secrets and grounded against retrieved
  evidence.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from memory_agent.config import AgentSettings, ContextMode
from memory_agent.core.confidence import EvidenceAssessment, EvidenceAssessor
from memory_agent.core.context_builder import ContextBuilder
from memory_agent.core.exceptions import (
    AgentError,
    InvalidRequestError,
    ProviderError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ResponseCancelledError,
    ToolRoundsExceededError,
)
from memory_agent.core.intent import IntentClassifier
from memory_agent.core.prompts import build_system_instruction
from memory_agent.models.suggestion import Suggestion
from memory_agent.models.tool_result import ToolCall, ToolResult, ToolTraceEntry
from memory_agent.providers.base import AIProvider
from memory_agent.providers.schemas import (
    ProviderMessage,
    ProviderRequest,
    ProviderResponse,
    ProviderRole,
    ToolResultPayload,
    Usage,
)
from memory_agent.security.data_filter import redact_text
from memory_agent.security.permission_guard import PermissionGuard
from memory_agent.tools.registry import ToolRegistry

logger = logging.getLogger("memory_agent.orchestrator")

HARD_MAX_TOOL_ROUNDS = 5
MAX_USER_INPUT_CHARS = 4000

_LIMIT_MESSAGE = (
    "I reached the limit of information lookups for one question. I may not have "
    "found everything. Please ask a more specific question so I can search again."
)


class CancellationToken:
    """Cooperative cancellation shared between the UI worker and the agent."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise ResponseCancelledError("The request was cancelled by the user.")


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = 3
    base_delay_s: float = 0.6
    max_delay_s: float = 5.0

    def delay_for(self, attempt: int, retry_after: Optional[float] = None) -> float:
        if retry_after is not None:
            return max(0.0, min(float(retry_after), self.max_delay_s))
        return min(self.base_delay_s * (2 ** attempt), self.max_delay_s)


class AgentTurnResult(BaseModel):
    """Everything the UI and persistence layer need for one user turn."""

    model_config = ConfigDict(extra="forbid")

    text: str
    evidence: EvidenceAssessment
    suggestions: list[Suggestion] = Field(default_factory=list)
    tool_trace: list[ToolTraceEntry] = Field(default_factory=list)
    usage: Optional[Usage] = None
    provider_id: str = ""
    model: Optional[str] = None
    context_mode: ContextMode = ContextMode.MINIMAL
    context_summary: str = ""
    rounds: int = 0
    cancelled: bool = False
    error_code: Optional[str] = None
    injection_flags: list[str] = Field(default_factory=list)
    latency_ms: int = 0

    def evidence_dict(self) -> dict[str, Any]:
        return {
            "grounding": self.evidence.grounding.value,
            "record_count": self.evidence.record_count,
            "sources": [source.model_dump() for source in self.evidence.sources],
            "conflicts": self.evidence.conflicts,
            "summary": self.evidence.summary_for_user(),
        }


class Orchestrator:
    def __init__(
        self,
        *,
        registry: ToolRegistry,
        context_builder: ContextBuilder,
        guard: PermissionGuard,
        classifier: Optional[IntentClassifier] = None,
        assessor: Optional[EvidenceAssessor] = None,
        retry_policy: Optional[RetryPolicy] = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._registry = registry
        self._context_builder = context_builder
        self._guard = guard
        self._classifier = classifier or IntentClassifier()
        self._assessor = assessor or EvidenceAssessor()
        self._retry = retry_policy or RetryPolicy()
        self._sleep = sleeper

    # ------------------------------------------------------------------ #
    # Public entry point
    # ------------------------------------------------------------------ #
    def run(
        self,
        *,
        user_id: str,
        user_text: str,
        settings: AgentSettings,
        provider: AIProvider,
        history: Optional[Sequence[ProviderMessage]] = None,
        conversation_id: Optional[str] = None,
        token: Optional[CancellationToken] = None,
    ) -> AgentTurnResult:
        started = time.monotonic()
        token = token or CancellationToken()

        text = (user_text or "").strip()
        if not text:
            raise InvalidRequestError("Empty user message.", user_message="Type a question first.")
        if len(text) > MAX_USER_INPUT_CHARS:
            raise InvalidRequestError(
                "User message exceeded the input limit.",
                user_message=f"Please keep your question under {MAX_USER_INPUT_CHARS} characters.",
            )

        self._guard.ensure_session(user_id)
        token.check()

        intent = self._classifier.classify(text)
        bundle = self._context_builder.build(
            user_id=user_id,
            query=text,
            mode=settings.context_mode,
            intent=intent,
            settings=settings,
            provider_is_local=provider.is_local,
            conversation_id=conversation_id,
        )
        token.check()

        max_rounds = max(1, min(settings.max_tool_rounds, HARD_MAX_TOOL_ROUNDS))
        self._registry.begin_turn(settings.max_tool_calls_per_turn)

        system_instruction = build_system_instruction(
            mode=settings.context_mode,
            intent=intent,
            max_answer_chars=settings.max_response_chars,
            has_records=bundle.has_records,
            flagged_records=bundle.injection.has_findings,
        )

        messages: list[ProviderMessage] = list(history or [])
        messages.append(
            ProviderMessage(
                role=ProviderRole.USER,
                text=self._compose_user_message(text, bundle.rendered, bundle),
            )
        )

        tool_results: list[ToolResult] = []
        suggestions: list[Suggestion] = []
        trace: list[ToolTraceEntry] = []
        usage_total = Usage()
        final_text: Optional[str] = None
        rounds_used = 0
        error_code: Optional[str] = None
        model_used = settings.model_for(provider.provider_id)

        for round_index in range(max_rounds):
            token.check()
            rounds_used = round_index + 1
            request = ProviderRequest(
                system_instruction=system_instruction,
                messages=messages,
                tools=[spec.model_dump() for spec in self._registry.specs()],
                model=settings.model_for(provider.provider_id),
                temperature=settings.temperature,
                max_output_tokens=1024,
                timeout_s=settings.provider_timeout_s,
            )
            response = self._generate_with_retry(provider, request, token)
            _accumulate_usage(usage_total, response.usage)
            model_used = response.model or model_used

            if not response.tool_calls:
                final_text = response.text or ""
                break

            if round_index == max_rounds - 1:
                # Budget exhausted: ask once for a final answer with tools off.
                messages.append(
                    ProviderMessage(
                        role=ProviderRole.ASSISTANT,
                        text=response.text or "",
                        tool_calls=response.tool_calls,
                    )
                )
                messages.append(
                    ProviderMessage(
                        role=ProviderRole.USER,
                        text=(
                            "Lookup limit reached. Do not request more tools. Answer now "
                            "using only the tool results already provided, and say what "
                            "could not be checked."
                        ),
                    )
                )
                error_code = ToolRoundsExceededError.code
                try:
                    forced_request = request.model_copy(
                        update={"messages": messages, "tools": []}
                    )
                    forced = self._generate_with_retry(provider, forced_request, token)
                    _accumulate_usage(usage_total, forced.usage)
                    final_text = forced.text or _LIMIT_MESSAGE
                except AgentError:
                    final_text = _LIMIT_MESSAGE
                break

            messages.append(
                ProviderMessage(
                    role=ProviderRole.ASSISTANT,
                    text=response.text or "",
                    tool_calls=response.tool_calls,
                )
            )

            payloads: list[ToolResultPayload] = []
            for call in response.tool_calls:
                token.check()
                result, duplicate = self._execute_call(
                    call=call,
                    user_id=user_id,
                    settings=settings,
                    conversation_id=conversation_id,
                )
                tool_results.append(result)
                if result.suggestion is not None:
                    suggestions.append(result.suggestion)
                trace.append(
                    ToolTraceEntry(
                        call_id=call.id,
                        tool=call.name,
                        ok=result.ok,
                        error_code=result.error_code,
                        record_count=len(result.records),
                        duplicate=duplicate,
                        duration_ms=int(result.data.get("_duration_ms", 0) or 0),
                    )
                )
                payloads.append(
                    ToolResultPayload(
                        tool_call_id=call.id,
                        name=call.name,
                        content=result.model_content(settings.max_tool_result_chars),
                        is_error=not result.ok,
                    )
                )

            messages.append(ProviderMessage(role=ProviderRole.TOOL, tool_results=payloads))
        else:
            final_text = _LIMIT_MESSAGE
            error_code = ToolRoundsExceededError.code

        token.check()

        assessment = self._assessor.assess(
            query=text, intent=intent, results=tool_results
        )
        answer = self._assessor.enforce(
            final_text or _LIMIT_MESSAGE,
            assessment,
            intent,
            suggestions=suggestions,
        )
        answer = self._screen_output(answer, settings)

        if bundle.injection.has_findings:
            logger.warning(
                "Context contained instruction-like text in %d record(s); treated as data.",
                len(bundle.injection.flagged_record_ids),
            )

        latency_ms = int((time.monotonic() - started) * 1000)
        return AgentTurnResult(
            text=answer,
            evidence=assessment,
            suggestions=suggestions,
            tool_trace=trace,
            usage=usage_total if usage_total.total_tokens or usage_total.input_tokens else None,
            provider_id=response.provider_id or provider.provider_id,
            model=model_used,
            context_mode=settings.context_mode,
            context_summary=bundle.describe(),
            rounds=rounds_used,
            error_code=error_code,
            injection_flags=bundle.injection.flagged_record_ids,
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _execute_call(
        self,
        *,
        call: ToolCall,
        user_id: str,
        settings: AgentSettings,
        conversation_id: Optional[str],
    ) -> tuple[ToolResult, bool]:
        result = self._registry.execute(
            call,
            user_id=user_id,
            guard=self._guard,
            settings=settings,
            conversation_id=conversation_id,
        )
        duplicate = result.error_code == "duplicate_tool_call"
        return result, duplicate

    def _generate_with_retry(
        self,
        provider: AIProvider,
        request: ProviderRequest,
        token: CancellationToken,
    ) -> ProviderResponse:
        attempt = 0
        while True:
            token.check()
            try:
                response = provider.generate(request)
                token.check()
                return response
            except ProviderRateLimitError as exc:
                if attempt >= self._retry.max_attempts - 1:
                    raise
                delay = self._retry.delay_for(attempt, exc.retry_after)
                self._wait(delay, token)
            except (ProviderTimeoutError, ProviderUnavailableError):
                if attempt >= self._retry.max_attempts - 1:
                    raise
                delay = self._retry.delay_for(attempt)
                self._wait(delay, token)
            except ProviderError:
                raise
            attempt += 1

    def _wait(self, seconds: float, token: CancellationToken) -> None:
        remaining = seconds
        while remaining > 0:
            token.check()
            step = min(0.2, remaining)
            self._sleep(step)
            remaining -= step

    @staticmethod
    def _compose_user_message(text: str, rendered_context: str, bundle) -> str:
        parts = [f"User question:\n{text}"]
        if rendered_context:
            parts.append(rendered_context)
            if bundle.truncated:
                parts.append(
                    "Note: the authorized context was truncated to stay within privacy limits."
                )
        else:
            parts.append(
                "No personal records were retrieved for this question. If the question is "
                "about the user's own life, say that no record was found rather than guessing."
            )
        return "\n\n".join(parts)

    @staticmethod
    def _screen_output(answer: str, settings: AgentSettings) -> str:
        screened = redact_text(answer or "").strip()
        limit = max(200, settings.max_response_chars)
        if len(screened) > limit:
            screened = screened[:limit].rstrip() + "\n\n[Answer shortened to fit the display limit.]"
        return screened


def _accumulate_usage(total: Usage, usage: Optional[Usage]) -> None:
    if usage is None:
        return
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        value = getattr(usage, field)
        if value is None:
            continue
        current = getattr(total, field) or 0
        setattr(total, field, current + value)
