"""Exception hierarchy for the Personal Memory Agent.

Every exception carries a *user-safe* message (``user_message``) plus a stable
machine-readable ``code``.  Internal detail is available for structured logs but
must never be shown verbatim in the UI or written to chat history.
"""

from __future__ import annotations

from typing import Optional


class AgentError(Exception):
    """Base class for all agent errors.

    Parameters
    ----------
    message:
        Internal, developer-facing description (may contain technical detail).
    user_message:
        Short, safe, actionable message shown to the user. Must not contain
        secrets, stack traces, SQL or database paths.
    retryable:
        Whether a retry can plausibly succeed without user intervention.
    """

    code: str = "agent_error"
    default_user_message = "Something went wrong while handling your request."

    def __init__(
        self,
        message: str = "",
        *,
        user_message: Optional[str] = None,
        retryable: bool = False,
        details: Optional[dict] = None,
    ) -> None:
        super().__init__(message or self.default_user_message)
        self.message = message or self.default_user_message
        self.user_message = user_message or self.default_user_message
        self.retryable = retryable
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "user_message": self.user_message,
            "retryable": self.retryable,
        }

    def __str__(self) -> str:  # keep internal detail for logs
        return f"[{self.code}] {self.message}"


# --------------------------------------------------------------------------- #
# Configuration / credential errors
# --------------------------------------------------------------------------- #
class ConfigurationError(AgentError):
    code = "configuration_error"
    default_user_message = "The assistant is not configured correctly yet."


class MissingApiKeyError(ConfigurationError):
    code = "missing_api_key"
    default_user_message = "No API key is configured. Add one in Assistant settings."


class CredentialStoreUnavailableError(ConfigurationError):
    code = "credential_store_unavailable"
    default_user_message = (
        "Secure credential storage is unavailable on this computer, so the API key "
        "cannot be stored safely."
    )


class SecretNotFoundError(ConfigurationError):
    code = "secret_not_found"
    default_user_message = "No saved API key was found for this provider."


# --------------------------------------------------------------------------- #
# Provider errors
# --------------------------------------------------------------------------- #
class ProviderError(AgentError):
    code = "provider_error"
    default_user_message = "The AI provider could not complete the request."


class ProviderAuthError(ProviderError):
    code = "provider_auth_failed"
    default_user_message = "The API key was rejected. Check the key and try again."


class ProviderRateLimitError(ProviderError):
    code = "provider_rate_limited"
    default_user_message = (
        "The AI provider is rate limiting requests. Please wait a moment and try again."
    )

    def __init__(self, message: str = "", *, retry_after: Optional[float] = None, **kw) -> None:
        super().__init__(message, retryable=True, **kw)
        self.retry_after = retry_after


class ProviderTimeoutError(ProviderError):
    code = "provider_timeout"
    default_user_message = "The AI provider took too long to respond. Please try again."

    def __init__(self, message: str = "", **kw) -> None:
        super().__init__(message, retryable=True, **kw)


class ProviderUnavailableError(ProviderError):
    code = "provider_unavailable"
    default_user_message = "The AI provider is currently unavailable."

    def __init__(self, message: str = "", **kw) -> None:
        super().__init__(message, retryable=True, **kw)


class ProviderNetworkError(ProviderUnavailableError):
    code = "network_unavailable"
    default_user_message = "No network connection is available to reach the AI provider."


class UnsupportedModelError(ProviderError):
    code = "unsupported_model"
    default_user_message = "The selected model is not available for this provider."


class ProviderResponseError(ProviderError):
    code = "provider_malformed_response"
    default_user_message = "The AI provider returned a response that could not be understood."


class ProviderCapabilityError(ProviderError):
    code = "provider_capability_missing"
    default_user_message = "The selected provider does not support this feature."


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
class ToolError(AgentError):
    code = "tool_error"
    default_user_message = "An information lookup failed."


class UnknownToolError(ToolError):
    code = "unknown_tool"
    default_user_message = "The assistant requested an unavailable action."


class ToolValidationError(ToolError):
    code = "invalid_tool_arguments"
    default_user_message = "The assistant requested an action with invalid details."


class ToolPermissionError(ToolError):
    code = "tool_permission_denied"
    default_user_message = "You have not granted permission for that information."


class ToolTimeoutError(ToolError):
    code = "tool_timeout"
    default_user_message = "The information lookup took too long."

    def __init__(self, message: str = "", **kw) -> None:
        super().__init__(message, retryable=True, **kw)


class ToolExecutionError(ToolError):
    code = "tool_execution_failed"
    default_user_message = "The information lookup could not be completed."


class ToolLimitError(ToolError):
    code = "tool_limit_exceeded"
    default_user_message = "The assistant requested too many lookups for one question."


# --------------------------------------------------------------------------- #
# Security / session / privacy
# --------------------------------------------------------------------------- #
class AuthenticationRequiredError(AgentError):
    code = "authentication_required"
    default_user_message = "You need to sign in before using the assistant."


class SessionExpiredError(AuthenticationRequiredError):
    code = "session_expired"
    default_user_message = "Your session has expired. Please sign in again."


class PermissionDeniedError(AgentError):
    code = "permission_denied"
    default_user_message = "Permission for that information has not been granted."


class ConsentRequiredError(AgentError):
    code = "consent_required"
    default_user_message = (
        "Full context sharing requires your explicit consent. Review and enable it "
        "in Assistant settings first."
    )


class LocalOnlyUnavailableError(AgentError):
    code = "local_only_unavailable"
    default_user_message = (
        "Local-only mode needs a local AI model. No local provider is configured."
    )


class StorageUnavailableError(AgentError):
    code = "storage_unavailable"
    default_user_message = "The memory database is currently unavailable."


class RecordNotFoundError(AgentError):
    code = "record_not_found"
    default_user_message = "That record could not be found."


class InvalidRequestError(AgentError):
    code = "invalid_request"
    default_user_message = "The request could not be processed as asked."


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
class ToolRoundsExceededError(AgentError):
    code = "tool_rounds_exceeded"
    default_user_message = (
        "I reached the limit of information lookups for one question. "
        "Please ask a more specific question."
    )


class ResponseCancelledError(AgentError):
    code = "cancelled"
    default_user_message = "The request was cancelled."


class AgentDisabledError(AgentError):
    code = "agent_disabled"
    default_user_message = "The assistant is turned off. Enable it in Assistant settings."


# --------------------------------------------------------------------------- #
# Voice
# --------------------------------------------------------------------------- #
class VoiceError(AgentError):
    code = "voice_error"
    default_user_message = "The voice feature could not be used."


class MicrophoneUnavailableError(VoiceError):
    code = "microphone_unavailable"
    default_user_message = (
        "No microphone is available. Check that one is connected and that microphone "
        "access is allowed for this app."
    )


class RecordingError(VoiceError):
    code = "recording_failed"
    default_user_message = "The recording could not be started or saved."


class TranscriptionError(VoiceError):
    code = "transcription_failed"
    default_user_message = "The recording could not be transcribed. Please try again or type instead."


class SpeechSynthesisError(VoiceError):
    code = "speech_synthesis_failed"
    default_user_message = "The answer could not be read aloud on this computer."


class CloudTranscriptionConsentError(VoiceError):
    code = "cloud_transcription_consent_required"
    default_user_message = (
        "Sending audio to a cloud service requires your explicit consent. "
        "Enable it in Assistant settings or use local transcription."
    )
