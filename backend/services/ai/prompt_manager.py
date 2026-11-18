"""
MEMOSPHERE Prompt Manager
Constructs grounded, privacy-preserving prompts for:
1. Natural Language Memory Q&A (strictly grounded in retrieved SQLite records, patient repetition support).
2. Quick Voice & Text Brain Dump Extraction (structured JSON output across 5 categories).
"""
import json
from datetime import date


class PromptManager:
    """Builds system and user prompts for external AI providers without leaking full databases."""

    SUPPORTED_CATEGORIES = ["People", "Places", "Items", "Activities", "Routines"]

    @classmethod
    def build_qa_messages(
        cls,
        question: str,
        retrieved_memories: list[dict],
        recent_conversations: list[dict] | None = None,
        is_repeated_question: bool = False,
        repetition_count: int = 0,
    ) -> list[dict]:
        """
        Construct messages for Natural Language Memory Q&A.
        Only the top relevant SQLite records are included.
        """
        memory_context_lines = []
        for idx, mem in enumerate(retrieved_memories[:8], start=1):
            line = (
                f"[Memory #{mem.get('id', idx)}] "
                f"Category: {mem.get('category', 'General')} | "
                f"Title: {mem.get('title', '')} | "
                f"Content: {mem.get('content', '')}"
            )
            if mem.get("entity_name"):
                line += f" | Entity: {mem.get('entity_name')}"
            if mem.get("location"):
                line += f" | Location: {mem.get('location')}"
            if mem.get("event_date"):
                line += f" | Date: {mem.get('event_date')}"
            memory_context_lines.append(line)

        memories_block = (
            "\n".join(memory_context_lines)
            if memory_context_lines
            else "NO_RELEVANT_MEMORIES_FOUND"
        )

        history_lines = []
        if recent_conversations:
            for turn in recent_conversations[-3:]:
                history_lines.append(f"User asked: {turn.get('question', '')}")
                history_lines.append(f"Assistant answered: {turn.get('answer', '')}")
        history_block = "\n".join(history_lines) if history_lines else "None"

        repetition_instruction = (
            f"NOTE: The user has asked this or a very similar question {repetition_count + 1} times recently. "
            "Respond with extra warmth, reassurance, and patience (e.g., end with 'Happy to remind you anytime!'). "
            "NEVER express irritation, impatience, or mention that they already asked."
            if is_repeated_question
            else "Respond warmly, clearly, and patiently."
        )

        system_prompt = (
            "You are MEMOSPHERE, a compassionate, privacy-first personal AI memory companion.\n"
            "STRICT RULES:\n"
            "1. Answer ONLY using the SAVED MEMORIES provided below.\n"
            "2. DO NOT invent, assume, or extrapolate personal facts, locations, people, or dates.\n"
            "3. If NO_RELEVANT_MEMORIES_FOUND or none of the saved memories answer the question, state gently and clearly that no matching memory was found yet, and offer to help save it.\n"
            "4. Keep your answer concise (1-3 sentences), reassuring, and easy to understand.\n"
            f"5. {repetition_instruction}"
        )

        user_prompt = (
            f"SAVED MEMORIES:\n{memories_block}\n\n"
            f"RECENT CONVERSATION CONTEXT:\n{history_block}\n\n"
            f"USER QUESTION:\n{question}\n\n"
            "Provide a direct, supportive answer grounded strictly in the saved memories above:"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    @classmethod
    def build_extraction_messages(cls, raw_text: str, reference_date: str | None = None) -> list[dict]:
        """
        Construct messages for Brain Dump structured JSON extraction.
        """
        today_str = reference_date or date.today().isoformat()
        schema_example = {
            "category": "People | Places | Items | Activities | Routines",
            "title": "Short descriptive title (2-5 words)",
            "content": "Clean summary of the memory",
            "entity_name": "Key person, object, or routine name (or empty string)",
            "location": "Specific location/place mentioned (or empty string)",
            "event_date": "YYYY-MM-DD date if mentioned or resolved from relative terms like yesterday/today",
            "needs_clarification": False,
            "clarification_question": "",
        }

        system_prompt = (
            "You are MEMOSPHERE's structured memory extraction engine.\n"
            f"Reference Current Date: {today_str}\n"
            "Extract structured information from the user's natural language input into valid JSON ONLY.\n"
            "Supported categories (choose the single best fit):\n"
            "- People (meetings, conversations, family, friends, doctors, contacts)\n"
            "- Places (visited locations, shops, clinics, addresses)\n"
            "- Items (where objects like keys, chargers, glasses, documents, or medicines are kept)\n"
            "- Activities (one-off events, walks, tasks completed, hobbies)\n"
            "- Routines (daily habits, medication schedules, recurring health/wellness routines)\n\n"
            "If critical details are ambiguous (for example, 'I put my medicine somewhere safe' without saying where), "
            "set 'needs_clarification': true and provide a gentle 'clarification_question'.\n"
            "Return ONLY a single raw JSON object matching this structure (no markdown code fences, no extra prose):\n"
            f"{json.dumps(schema_example, indent=2)}"
        )

        user_prompt = f"Extract structured memory JSON from this input:\n\"{raw_text}\""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
