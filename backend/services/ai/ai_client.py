"""
MEMOSPHERE AI Client & Common Provider Interface
IMPORTANT ARCHITECTURAL DECISION:
Does NOT implement or train any custom ML/neural model.
Provides:
1. BaseAIProvider common interface for external AI APIs (Groq, NVIDIA NIM, Gemini, OpenAI).
2. Privacy-safe error logging (never logs personal memories or API keys).
3. Transparent rule-based local fallback when no API key is configured or when an external API is unreachable.
"""
from abc import ABC, abstractmethod
from datetime import date, timedelta
import logging
import re

from config import Config
from backend.services.ai.prompt_manager import PromptManager
from backend.services.ai.response_parser import ResponseParser

logger = logging.getLogger("memosphere.ai")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] [MEMOSPHERE-AI] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class AIProviderError(Exception):
    """Sanitized exception for AI API errors (never contains API keys or personal memory text)."""

    def __init__(self, message: str, error_code: str = "api_error", status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


class BaseAIProvider(ABC):
    """Common interface that all external AI provider clients must implement."""

    provider_name: str = "base"

    def __init__(self, api_key: str, model: str, timeout: int = 15):
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.timeout = timeout

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @abstractmethod
    def generate_completion(self, messages: list[dict], json_mode: bool = False) -> str:
        """Send messages to the external AI provider and return raw completion text."""
        raise NotImplementedError

    def generate_response(self, messages: list[dict], json_mode: bool = False) -> str:
        """Common contract: return a sanitized text response from the provider."""
        return ResponseParser.sanitize_text(
            self.generate_completion(messages=messages, json_mode=json_mode)
        )

    def answer_memory_question(
        self,
        question: str,
        retrieved_memories: list[dict],
        recent_conversations: list[dict] | None = None,
        is_repeated_question: bool = False,
        repetition_count: int = 0,
    ) -> str:
        """Common contract: grounded Q&A built from retrieved SQLite records only."""
        messages = PromptManager.build_qa_messages(
            question=question,
            retrieved_memories=retrieved_memories,
            recent_conversations=recent_conversations,
            is_repeated_question=is_repeated_question,
            repetition_count=repetition_count,
        )
        return self.generate_response(messages=messages, json_mode=False)

    def extract_memories(self, raw_text: str, reference_date: str | None = None) -> dict:
        """Common contract: structured memory extraction with validated JSON output."""
        messages = PromptManager.build_extraction_messages(
            raw_text=raw_text, reference_date=reference_date
        )
        raw_json = self.generate_completion(messages=messages, json_mode=True)
        return ResponseParser.parse_extraction_json(
            raw_json, original_text=raw_text, reference_date=reference_date
        )

    def classify_information(self, raw_text: str, reference_date: str | None = None) -> dict:
        """Common contract: classify (and extract) information into the 5 memory categories."""
        return self.extract_memories(raw_text=raw_text, reference_date=reference_date)

    def test_connection(self) -> dict:
        """Verify API key and connectivity with a minimal ping request."""
        if not self.is_configured():
            return {
                "connected": False,
                "provider": self.provider_name,
                "model": self.model,
                "mode": "rule_based_fallback",
                "message": f"No API key configured for {self.provider_name.upper()}. Running in local rule-based fallback mode.",
            }
        try:
            reply = self.generate_completion(
                messages=[
                    {"role": "system", "content": "Reply with the single word OK."},
                    {"role": "user", "content": "Ping"},
                ],
                json_mode=False,
            )
            return {
                "connected": True,
                "provider": self.provider_name,
                "model": self.model,
                "mode": "external_api",
                "message": f"Successfully connected to {self.provider_name.upper()} ({self.model}).",
                "sample_reply": ResponseParser.sanitize_text(reply)[:40],
            }
        except AIProviderError as exc:
            logger.warning(
                "Connectivity check failed for provider=%s code=%s",
                self.provider_name,
                exc.error_code,
            )
            return {
                "connected": False,
                "provider": self.provider_name,
                "model": self.model,
                "mode": "rule_based_fallback",
                "error_code": exc.error_code,
                "message": exc.message,
            }


class RuleBasedFallbackEngine:
    """
    Transparent, deterministic rule-based fallback used ONLY when no external API key
    is configured or when an external API call fails. Never pretends to be a neural AI model.
    """

    @classmethod
    def answer_from_memories(
        cls,
        question: str,
        retrieved_memories: list[dict],
        is_repeated_question: bool = False,
        repetition_count: int = 0,
    ) -> str:
        if not retrieved_memories:
            reassurance = " Happy to check again anytime!" if is_repeated_question else ""
            return (
                "I couldn't find any saved memory matching that yet. "
                "You can add it anytime using Brain Dump or voice capture!" + reassurance
            )

        top = retrieved_memories[0]
        content = top.get("content", "").strip().rstrip(".")
        location = top.get("location", "").strip()
        entity = top.get("entity_name", "").strip()
        event_date = top.get("event_date", "").strip()

        q_lower = question.lower()
        if is_repeated_question:
            if "where" in q_lower and location and entity:
                return f"Your {entity.lower()} is in the {location.lower()} ({content}). Happy to remind you!"
            return f"{content}. Happy to remind you anytime!"

        if "where" in q_lower and location and entity:
            return f"You saved that your {entity.lower()} is at/in {location} ({content})."
        if "when" in q_lower and event_date:
            return f"You recorded: {content} (Date: {event_date})."
        return f"You saved that: {content}."

    @classmethod
    def extract_structured_memory(cls, raw_text: str, reference_date: str | None = None) -> dict:
        text = (raw_text or "").strip()
        ref_dt = date.fromisoformat(reference_date) if reference_date else date.today()
        event_date_str = ref_dt.isoformat()

        lower = text.lower()
        if "yesterday" in lower:
            event_date_str = (ref_dt - timedelta(days=1)).isoformat()
        elif "tomorrow" in lower:
            event_date_str = (ref_dt + timedelta(days=1)).isoformat()
        else:
            date_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
            if date_match:
                event_date_str = date_match.group(1)

        category = "Activities"
        title = ""
        entity_name = ""
        location = ""
        needs_clarification = False
        clarification_question = ""

        # Pattern 1: People ("I met Rahul at the workshop yesterday", "Spoke with Dr. Patel at Clinic")
        met_match = re.search(
            r"\b(?:met|saw|visited|called|talked to|spoke with|with)\s+([A-Z][a-zA-Z0-9_.\s]{1,35}?)(?:\s+(?:at|in|near|on|yesterday|today|last)\b|[.,;]|$)",
            text,
        )
        # Pattern 2: Items ("I kept my house keys in the blue bag", "My charger is on the study desk")
        kept_match = re.search(
            r"\b(?:kept|put|left|placed|stored|hid)\s+(?:my\s+|the\s+)?([a-zA-Z0-9\s]{2,35}?)\s+(?:in|on|inside|under|at|near)\s+(?:the\s+|my\s+)?([a-zA-Z0-9\s]{2,40}?)(?:\s+(?:yesterday|today|this morning)|[.,;]|$)",
            text,
            flags=re.IGNORECASE,
        )
        is_item_location = re.search(
            r"\b(?:my|the)\s+([a-zA-Z0-9\s]{2,30}?)\s+(?:is|are)\s+(?:in|on|inside|under|at)\s+(?:the\s+|my\s+)?([a-zA-Z0-9\s]{2,40}?)(?:[.,;]|$)",
            text,
            flags=re.IGNORECASE,
        )

        # Check ambiguous item storage ("I put my keys somewhere", "I kept my glasses")
        ambiguous_item = re.search(
            r"\b(?:kept|put|left|placed|stored)\s+(?:my\s+|the\s+)?([a-zA-Z0-9\s]{2,30}?)(?:\s+somewhere|\s+away|\s+safe)?$",
            text.rstrip(".,!"),
            flags=re.IGNORECASE,
        )

        if kept_match:
            category = "Items"
            entity_name = kept_match.group(1).strip().title()
            location = kept_match.group(2).strip().title()
            title = f"{entity_name} Location"
        elif is_item_location and any(
            w in lower
            for w in ["charger", "key", "keys", "glasses", "wallet", "phone", "watch", "bag", "medicine", "pill", "passport", "card", "remote", "book"]
        ):
            category = "Items"
            entity_name = is_item_location.group(1).strip().title()
            location = is_item_location.group(2).strip().title()
            title = f"{entity_name} Location"
        elif ambiguous_item and not any(prep in lower for prep in [" in ", " on ", " under ", " inside ", " at ", " near "]):
            category = "Items"
            entity_name = ambiguous_item.group(1).strip().title()
            title = f"{entity_name} Location"
            needs_clarification = True
            clarification_question = f"Where specifically did you keep your {entity_name.lower()} so I can remember the exact spot for you?"
        elif met_match or any(w in lower for w in ["met ", "doctor", "friend", "neighbor", "son", "daughter", "sister", "brother", "nurse"]):
            category = "People"
            if met_match:
                entity_name = met_match.group(1).strip()
                title = f"Met {entity_name}"
            else:
                name_caps = re.findall(r"\b([A-Z][a-z]{2,20})\b", text[1:])
                entity_name = name_caps[0] if name_caps else "Contact"
                title = f"Note about {entity_name}"
            loc_match = re.search(r"\b(?:at|in)\s+(?:the\s+)?([a-zA-Z0-9\s]{2,35}?)(?:\s+(?:yesterday|today|on\b|at\s+\d)|[.,;]|$)", text, flags=re.IGNORECASE)
            if loc_match:
                # Preserve original casing after the first letter ("college workshop"
                # must not become "College Workshop").
                location = ResponseParser.smart_title(loc_match.group(1))
        elif any(w in lower for w in ["walk", "exercise", "medication", "vitamin", "breakfast", "dinner", "lunch", "yoga", "sleep", "routine", "completed my", "took my"]):
            if any(w in lower for w in ["daily", "every day", "routine", "morning medication", "evening walk", "morning walk", "pill", "insulin", "tablet"]):
                category = "Routines"
            else:
                category = "Activities"
            act_match = re.search(
                r"\b(?:completed|finished|did|took|went for)\s+(?:my\s+|the\s+|an?\s+)?([a-zA-Z0-9\s]{3,35}?)(?:\s+(?:at|in|on|yesterday|today)\b|[.,;]|$)",
                text,
                flags=re.IGNORECASE,
            )
            if act_match:
                entity_name = act_match.group(1).strip().title()
                title = f"Completed {entity_name}"
            else:
                entity_name = "Daily Activity"
                title = " ".join(text.split()[:4]).rstrip(".,;").title()
            time_match = re.search(r"\bat\s+(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm)?)", text)
            if time_match:
                location = f"At {time_match.group(1).strip()}"
        elif any(w in lower for w in ["visited", "went to", "park", "hospital", "pharmacy", "market", "temple", "church", "cafe", "library", "store"]):
            category = "Places"
            place_match = re.search(r"\b(?:visited|went to|at)\s+(?:the\s+)?([a-zA-Z0-9\s]{2,35}?)(?:\s+(?:yesterday|today)|[.,;]|$)", text, flags=re.IGNORECASE)
            if place_match:
                location = ResponseParser.smart_title(place_match.group(1))
                entity_name = location
                title = f"Visited {location}"
            else:
                title = "Visited Place"

        clean_content = re.sub(r"^i\s+", "", text.strip(), flags=re.IGNORECASE).rstrip(".")
        clean_content = re.sub(r"\s+yesterday$", "", clean_content, flags=re.IGNORECASE)
        if clean_content:
            clean_content = clean_content[0].upper() + clean_content[1:]

        if not title:
            words = (clean_content or text).split()
            title = " ".join(words[:4]).rstrip(".,;!?").title() or "Saved Memory"

        if len(text.split()) < 3 and not entity_name:
            needs_clarification = True
            clarification_question = "Could you share a few more details (such as what item, person, or location you'd like me to remember)?"

        return ResponseParser.normalize_extracted_dict(
            {
                "category": category,
                "title": title,
                "content": clean_content or text,
                "entity_name": entity_name,
                "location": location,
                "event_date": event_date_str,
                "needs_clarification": needs_clarification,
                "clarification_question": clarification_question,
            },
            original_text=text,
            reference_date=event_date_str,
        )


class AIClient:
    """
    High-level AI integration facade used by application routes and services.
    Switches between Groq, NVIDIA NIM, Gemini and OpenAI via ProviderFactory without altering
    business logic, and falls back cleanly when no API key is configured.
    """

    def __init__(self, provider_override: BaseAIProvider | None = None):
        self._provider_override = provider_override

    def get_provider(self) -> BaseAIProvider:
        if self._provider_override is not None:
            return self._provider_override
        from backend.services.ai.provider_factory import ProviderFactory
        return ProviderFactory.create_provider()

    def answer_memory_question(
        self,
        question: str,
        retrieved_memories: list[dict],
        recent_conversations: list[dict] | None = None,
        is_repeated_question: bool = False,
        repetition_count: int = 0,
    ) -> dict:
        provider = self.get_provider()

        if provider.is_configured():
            try:
                clean_reply = provider.answer_memory_question(
                    question=question,
                    retrieved_memories=retrieved_memories,
                    recent_conversations=recent_conversations,
                    is_repeated_question=is_repeated_question,
                    repetition_count=repetition_count,
                )
                if clean_reply:
                    return {
                        "answer": clean_reply,
                        "provider": provider.provider_name,
                        "model": provider.model,
                        "source_mode": "external_ai_api",
                        "used_fallback": False,
                    }
            except AIProviderError as exc:
                logger.warning(
                    "External AI Q&A failed (provider=%s, code=%s). Using local rule-based fallback.",
                    provider.provider_name,
                    exc.error_code,
                )
                fallback_answer = RuleBasedFallbackEngine.answer_from_memories(
                    question=question,
                    retrieved_memories=retrieved_memories,
                    is_repeated_question=is_repeated_question,
                    repetition_count=repetition_count,
                )
                return {
                    "answer": fallback_answer,
                    "provider": provider.provider_name,
                    "model": provider.model,
                    "source_mode": "rule_based_fallback",
                    "used_fallback": True,
                    "api_warning": exc.message,
                }

        fallback_answer = RuleBasedFallbackEngine.answer_from_memories(
            question=question,
            retrieved_memories=retrieved_memories,
            is_repeated_question=is_repeated_question,
            repetition_count=repetition_count,
        )
        return {
            "answer": fallback_answer,
            "provider": provider.provider_name,
            "model": provider.model,
            "source_mode": "rule_based_fallback",
            "used_fallback": True,
        }

    def extract_memory(self, raw_text: str, reference_date: str | None = None) -> dict:
        provider = self.get_provider()

        if provider.is_configured():
            try:
                parsed = provider.extract_memories(
                    raw_text=raw_text, reference_date=reference_date
                )
                return {
                    "extracted": parsed,
                    "provider": provider.provider_name,
                    "model": provider.model,
                    "source_mode": "external_ai_api",
                    "used_fallback": False,
                }
            except (AIProviderError, ValueError) as exc:
                err_code = getattr(exc, "error_code", "parse_error")
                logger.warning(
                    "External AI extraction failed (provider=%s, code=%s). Using local rule-based fallback.",
                    provider.provider_name,
                    err_code,
                )
                parsed = RuleBasedFallbackEngine.extract_structured_memory(
                    raw_text=raw_text, reference_date=reference_date
                )
                # Never echo raw exception text: it may contain raw model output fragments.
                if isinstance(exc, AIProviderError):
                    safe_warning = exc.message
                else:
                    safe_warning = (
                        "The AI provider returned an unexpected response format. "
                        "A local rule-based result was used instead."
                    )
                return {
                    "extracted": parsed,
                    "provider": provider.provider_name,
                    "model": provider.model,
                    "source_mode": "rule_based_fallback",
                    "used_fallback": True,
                    "api_warning": safe_warning,
                }

        parsed = RuleBasedFallbackEngine.extract_structured_memory(
            raw_text=raw_text, reference_date=reference_date
        )
        return {
            "extracted": parsed,
            "provider": provider.provider_name,
            "model": provider.model,
            "source_mode": "rule_based_fallback",
            "used_fallback": True,
        }

    def get_status(self, verify_live: bool = False) -> dict:
        provider = self.get_provider()
        configured = provider.is_configured()
        status_info = {
            "selected_provider": provider.provider_name,
            "selected_model": provider.model,
            "api_key_configured": configured,
            "masked_api_key": Config.mask_api_key(provider.api_key),
            "active_mode": "external_ai_api" if configured else "rule_based_fallback",
            "supported_providers": [
                {
                    "id": prov,
                    "name": Config.PROVIDER_DISPLAY_NAMES.get(prov, prov.upper()),
                    "configured": bool(Config.get_api_key(prov)),
                    "default_model": Config.DEFAULT_MODELS.get(prov, ""),
                    "model": Config.get_ai_model(prov),
                }
                for prov in Config.PROVIDER_KEY_ENV
            ],
        }
        if verify_live:
            status_info["connectivity"] = provider.test_connection()
        return status_info
