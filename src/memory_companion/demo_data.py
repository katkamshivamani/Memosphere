"""Demo data for development and evaluation.

The desktop app never seeds data automatically.  Use ``scripts/seed_demo.py`` or
the login screen's "Create account" flow instead.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from memory_companion.composition import AppContext


def seed_for_user(ctx: AppContext, user_id: str) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    counts = {"memories": 0, "people": 0, "places": 0, "activities": 0, "routines": 0, "reminders": 0}

    wallet = ctx.memories.create_memory(
        user_id,
        {
            "title": "Wallet location",
            "content": "Wallet was placed in the top drawer of the study desk after paying the electricity bill.",
            "category": "objects",
        },
    )
    ctx.memories.create_memory(
        user_id,
        {
            "title": "Spare keys",
            "content": "Spare house keys are in the blue bowl on the kitchen counter.",
            "category": "objects",
        },
    )
    ctx.memories.create_memory(
        user_id,
        {
            "title": "Passport folder",
            "content": "Passport and insurance papers are kept in the bedroom safe.",
            "category": "documents",
        },
    )
    ctx.memories.create_memory(
        user_id,
        {
            "title": "Garden watering",
            "content": "Tomatoes are watered every second evening; the rose bed on Sunday mornings.",
            "category": "routines",
        },
    )
    counts["memories"] = 4

    sarah = ctx.people.create_person(
        user_id,
        {
            "name": "Sarah",
            "relationship": "daughter",
            "notes": "Calls on Sunday evenings. Lives nearby and visits on Saturdays.",
        },
    )
    dr_patel = ctx.people.create_person(
        user_id,
        {
            "name": "Dr. Patel",
            "relationship": "doctor",
            "notes": "Primary care physician at the Riverside Clinic.",
        },
    )
    ctx.people.create_relationship(
        user_id, sarah["id"], {"relationship": "daughter", "notes": "Emergency contact."}
    )
    ctx.people.create_relationship(
        user_id, dr_patel["id"], {"relationship": "doctor", "notes": "Riverside Clinic, second floor."}
    )
    counts["people"] = 2

    study = ctx.places.create_place(
        user_id,
        {"name": "Study", "category": "room", "description": "Desk, bookshelf and filing cabinet."},
    )
    ctx.places.create_place(
        user_id,
        {
            "name": "Kitchen",
            "category": "room",
            "description": "Blue bowl on the counter holds keys and small items.",
        },
    )
    ctx.places.create_place(
        user_id,
        {
            "name": "Riverside Clinic",
            "category": "medical",
            "description": "Dr. Patel works here. Appointments are on the second floor.",
        },
    )
    counts["places"] = 3

    ctx.activities.create_activity(
        user_id,
        {
            "name": "Morning medication",
            "description": "Took the morning blood-pressure tablet with breakfast.",
            "occurred_at": (now.replace(hour=8, minute=10)).isoformat(),
            "place_id": study["id"],
        },
    )
    ctx.activities.create_activity(
        user_id,
        {
            "name": "Walk in the park",
            "description": "Walked with Mark for about 40 minutes.",
            "occurred_at": (now - timedelta(days=1)).replace(hour=9, minute=0).isoformat(),
        },
    )
    ctx.activities.create_activity(
        user_id,
        {
            "name": "Dentist appointment",
            "description": "Routine check-up at Bright Smile Dental.",
            "occurred_at": (now - timedelta(days=7)).replace(hour=11, minute=0).isoformat(),
        },
    )
    counts["activities"] = 3

    medication = ctx.routines.create_routine(
        user_id,
        {
            "name": "Morning medication",
            "description": "Take the blood-pressure tablet with breakfast, then log it.",
            "schedule_hint": "Every day at 08:00",
        },
    )
    walk = ctx.routines.create_routine(
        user_id,
        {
            "name": "Evening walk",
            "description": "Short walk around the block after dinner.",
            "schedule_hint": "Every day around 19:00",
        },
    )
    ctx.routines.log_completion(user_id, medication["id"])
    counts["routines"] = 2

    ctx.reminders.create_reminder(
        user_id,
        {
            "title": "Dentist appointment",
            "description": "Bright Smile Dental, 10:30. Bring the insurance card.",
            "due_at": (now + timedelta(days=3)).replace(hour=10, minute=30).isoformat(),
        },
    )
    ctx.reminders.create_reminder(
        user_id,
        {
            "title": "Collect prescription refill",
            "description": "Riverside Pharmacy closes at 18:00.",
            "due_at": (now + timedelta(days=5)).replace(hour=16, minute=0).isoformat(),
        },
    )
    counts["reminders"] = 2

    return counts


def ensure_demo_user(ctx: AppContext, username: str = "demo", password: str = "demo-pass-1234"):
    """Create (or sign in to) a demo account and seed it once."""
    existing = ctx.auth.list_users()
    for user in existing:
        if user["username"] == username:
            ctx.auth.set_permission(user["id"], "memory.read", True)
            return user["id"], False
    session = ctx.auth.register(username, password, display_name="Demo User")
    seed_for_user(ctx, session.user_id)
    return session.user_id, True
