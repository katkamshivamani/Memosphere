"""
MEMOSPHERE Memory Service
Handles SQLite memory retrieval (keyword & entity scoring so the entire personal database
is NEVER sent to the external AI API), duplicate detection, and patient repetition detection.
"""
import re
from datetime import datetime
from backend.models import db, Memory, Conversation, utc_now


class MemoryService:
    """Service layer for memory CRUD, targeted SQLite retrieval, and patient Q&A context."""

    STOP_WORDS = {
        "a", "an", "the", "is", "are", "was", "were", "where", "when", "who",
        "what", "how", "did", "do", "does", "i", "my", "me", "mine", "keep",
        "kept", "put", "place", "placed", "left", "in", "on", "at", "to", "for",
        "of", "with", "about", "tell", "can", "you", "please", "find", "remember",
    }

    @classmethod
    def extract_keywords(cls, query_text: str) -> list[str]:
        tokens = re.findall(r"[a-zA-Z0-9]+", (query_text or "").lower())
        keywords = [t for t in tokens if t not in cls.STOP_WORDS and len(t) >= 2]
        # Handle simple plurals (e.g. keys -> key)
        expanded = []
        for kw in keywords:
            expanded.append(kw)
            if kw.endswith("s") and len(kw) > 3:
                expanded.append(kw[:-1])
        return list(dict.fromkeys(expanded))

    @classmethod
    def retrieve_relevant_memories(cls, user_id: int, question: str, max_results: int = 5) -> list[Memory]:
        """
        Retrieve only the most relevant SQLite records for a user's question.
        Never sends the entire personal database to the external AI API.
        """
        keywords = cls.extract_keywords(question)
        user_memories = (
            Memory.query.filter_by(user_id=user_id)
            .order_by(Memory.updated_at.desc())
            .all()
        )
        if not user_memories:
            return []

        if not keywords:
            return user_memories[:max_results]

        scored: list[tuple[int, Memory]] = []
        for mem in user_memories:
            haystack_title = (mem.title or "").lower()
            haystack_entity = (mem.entity_name or "").lower()
            haystack_content = (mem.content or "").lower()
            haystack_location = (mem.location or "").lower()
            haystack_category = (mem.category or "").lower()

            score = 0
            for kw in keywords:
                if kw in haystack_entity:
                    score += 6
                if kw in haystack_title:
                    score += 5
                if kw in haystack_content:
                    score += 3
                if kw in haystack_location:
                    score += 3
                if kw in haystack_category:
                    score += 1

            if score > 0:
                scored.append((score, mem))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:max_results]]

    @classmethod
    def check_duplicate_memory(
        cls,
        user_id: int,
        title: str,
        content: str,
        category: str,
        entity_name: str = "",
        location: str = "",
    ) -> Memory | None:
        """
        Check if an identical or near-duplicate memory already exists for this user.
        If the same item's location is updated or the exact same content exists, return it.
        """
        existing = Memory.query.filter_by(user_id=user_id).all()
        norm_content = re.sub(r"\s+", " ", (content or "").strip().lower()).rstrip(".")
        norm_title = re.sub(r"\s+", " ", (title or "").strip().lower()).rstrip(".")
        norm_entity = (entity_name or "").strip().lower()
        norm_loc = (location or "").strip().lower()

        for mem in existing:
            mem_content = re.sub(r"\s+", " ", (mem.content or "").strip().lower()).rstrip(".")
            mem_title = re.sub(r"\s+", " ", (mem.title or "").strip().lower()).rstrip(".")
            mem_entity = (mem.entity_name or "").strip().lower()
            mem_loc = (mem.location or "").strip().lower()

            if norm_content and norm_content == mem_content:
                return mem
            if (
                category == mem.category
                and norm_entity
                and norm_entity == mem_entity
                and norm_loc
                and norm_loc == mem_loc
            ):
                return mem
            if norm_title and norm_title == mem_title and norm_content == mem_content:
                return mem

        return None

    @classmethod
    def create_or_update_memory(
        cls,
        user_id: int,
        category: str,
        title: str,
        content: str,
        entity_name: str = "",
        location: str = "",
        event_date: str = "",
        prevent_duplicates: bool = True,
    ) -> tuple[Memory, bool]:
        """
        Create a new memory or return/update an existing duplicate.
        Returns (memory, is_duplicate).
        """
        if prevent_duplicates:
            dup = cls.check_duplicate_memory(
                user_id=user_id,
                title=title,
                content=content,
                category=category,
                entity_name=entity_name,
                location=location,
            )
            if dup is not None:
                dup.updated_at = utc_now()
                db.session.commit()
                return dup, True

        new_mem = Memory(
            user_id=user_id,
            category=category or "Items",
            title=title or "Saved Memory",
            content=content,
            entity_name=entity_name or "",
            location=location or "",
            event_date=event_date or datetime.now().strftime("%Y-%m-%d"),
        )
        db.session.add(new_mem)
        db.session.commit()
        return new_mem, False

    @classmethod
    def detect_repeated_question(cls, user_id: int, question: str) -> tuple[bool, int, list[Conversation]]:
        """
        Inspect recent conversation turns to see if the user is repeating a question.
        Enables patient, reassuring responses without irritation.
        """
        recent = (
            Conversation.query.filter_by(user_id=user_id)
            .order_by(Conversation.created_at.desc())
            .limit(10)
            .all()
        )
        if not recent:
            return False, 0, []

        q_keywords = set(cls.extract_keywords(question))
        q_norm = re.sub(r"[^a-z0-9\s]", "", (question or "").lower()).strip()

        repeat_count = 0
        for conv in recent:
            prev_norm = re.sub(r"[^a-z0-9\s]", "", (conv.question or "").lower()).strip()
            prev_keywords = set(cls.extract_keywords(conv.question or ""))
            if q_norm and q_norm == prev_norm:
                repeat_count += 1
            elif q_keywords and prev_keywords:
                overlap = len(q_keywords & prev_keywords) / max(len(q_keywords | prev_keywords), 1)
                if overlap >= 0.65:
                    repeat_count += 1

        return (repeat_count > 0), repeat_count, list(reversed(recent[:5]))
