import json
import os
import sqlite3
import hashlib
from datetime import datetime, timedelta
from config import settings

DB_PATH = settings.database_path


def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        settings.secret_key.encode("utf-8"),
        100_000,
    ).hex()


def init_db(force_reseed: bool = False):
    conn = get_db_connection()
    cur = conn.cursor()

    # 1. Existing Module A: People & Relationship Memory (Extended with photoCaption & sharedWithCaregiver)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            relationship TEXT NOT NULL,
            whereMet TEXT NOT NULL,
            keyFacts TEXT NOT NULL,
            importantDate TEXT,
            avatarUrl TEXT,
            photoCaption TEXT,
            voicePrompt TEXT,
            sharedWithCaregiver INTEGER NOT NULL DEFAULT 1,
            lastInteraction TEXT NOT NULL,
            createdAt TEXT NOT NULL
        )
    """)

    # Ensure backward-compatible columns if upgrading existing memosphere.db
    for col_def in [
        ("photoCaption", "TEXT"),
        ("voicePrompt", "TEXT"),
        ("sharedWithCaregiver", "INTEGER NOT NULL DEFAULT 1"),
    ]:
        try:
            cur.execute(f"ALTER TABLE people ADD COLUMN {col_def[0]} {col_def[1]}")
        except sqlite3.OperationalError:
            pass

    # 2. Existing Module B: Places & Item Finder
    cur.execute("""
        CREATE TABLE IF NOT EXISTS places (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            exactLocation TEXT NOT NULL,
            notes TEXT,
            isPinned INTEGER NOT NULL DEFAULT 0,
            sharedWithCaregiver INTEGER NOT NULL DEFAULT 1,
            updatedAt TEXT NOT NULL,
            createdAt TEXT NOT NULL
        )
    """)
    try:
        cur.execute("ALTER TABLE places ADD COLUMN sharedWithCaregiver INTEGER NOT NULL DEFAULT 1")
    except sqlite3.OperationalError:
        pass

    # 3. Existing Module C: Daily Activities & Action Log
    cur.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            id TEXT PRIMARY KEY,
            actionTitle TEXT NOT NULL,
            category TEXT NOT NULL,
            notes TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            loggedAt TEXT NOT NULL
        )
    """)

    # 4. Existing Module D: Routines & Habit Builder
    cur.execute("""
        CREATE TABLE IF NOT EXISTS routines (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            timeSlot TEXT NOT NULL,
            frequency TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'NORMAL',
            shareWithCircle INTEGER NOT NULL DEFAULT 0,
            completedToday INTEGER NOT NULL DEFAULT 0,
            lastCompletedAt TEXT,
            streakCount INTEGER NOT NULL DEFAULT 0,
            createdAt TEXT NOT NULL
        )
    """)

    # 5. New Module A3: Personal Life Story & Memory Album
    cur.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            storyText TEXT NOT NULL,
            eraOrYear TEXT,
            mediaUrl TEXT,
            favouriteMusic TEXT,
            involvedPeople TEXT,
            sharedWithCaregiver INTEGER NOT NULL DEFAULT 1,
            createdAt TEXT NOT NULL
        )
    """)

    # 6. New Module A4: Familiar Environment Guide
    cur.execute("""
        CREATE TABLE IF NOT EXISTS environment_guides (
            id TEXT PRIMARY KEY,
            locationName TEXT NOT NULL,
            visualIcon TEXT NOT NULL,
            stepByStepInstruction TEXT NOT NULL,
            spokenPrompt TEXT NOT NULL,
            roomCategory TEXT NOT NULL DEFAULT 'Home Indoor',
            isPinned INTEGER NOT NULL DEFAULT 1,
            updatedAt TEXT NOT NULL
        )
    """)

    # 7. New Module A5: Emergency SOS Contacts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS emergency_contacts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            relationship TEXT NOT NULL,
            phone TEXT NOT NULL,
            isPrimary INTEGER NOT NULL DEFAULT 0,
            homeAddress TEXT NOT NULL,
            medicalNotes TEXT
        )
    """)

    # 8. New Module A6: Medication Reminder & Confirmation
    cur.execute("""
        CREATE TABLE IF NOT EXISTS medications (
            id TEXT PRIMARY KEY,
            medicationName TEXT NOT NULL,
            dosageDisplay TEXT NOT NULL,
            scheduledTime TEXT NOT NULL,
            instructions TEXT NOT NULL,
            isCritical INTEGER NOT NULL DEFAULT 1,
            shareWithCaregiver INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'PENDING',
            lastConfirmedAt TEXT,
            snoozedUntil TEXT,
            createdAt TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS medication_logs (
            id TEXT PRIMARY KEY,
            medicationId TEXT NOT NULL,
            medicationName TEXT NOT NULL,
            action TEXT NOT NULL,
            confirmedBy TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            notes TEXT
        )
    """)

    # 9. New Module B: Persistent Vibration & Acknowledgement-Based Reminders
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            scheduledTime TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'Important',
            repeatIntervalSec INTEGER NOT NULL DEFAULT 120,
            snoozeDurationMins INTEGER NOT NULL DEFAULT 5,
            escalationWindowMins INTEGER NOT NULL DEFAULT 30,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            acknowledgedAt TEXT,
            snoozedUntil TEXT,
            retryCount INTEGER NOT NULL DEFAULT 0,
            shareWithCaregiver INTEGER NOT NULL DEFAULT 1,
            createdAt TEXT NOT NULL
        )
    """)

    # 10. New Module D3: Mood Check-ins
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mood_checkins (
            id TEXT PRIMARY KEY,
            mood TEXT NOT NULL,
            notes TEXT,
            sharedWithCaregiver INTEGER NOT NULL DEFAULT 1,
            loggedAt TEXT NOT NULL
        )
    """)

    # 11. New Module D4: Caregiver Notes, Appointments & Expected Visits
    cur.execute("""
        CREATE TABLE IF NOT EXISTS caregiver_notes (
            id TEXT PRIMARY KEY,
            authorName TEXT NOT NULL,
            noteType TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            scheduledFor TEXT,
            createdAt TEXT NOT NULL
        )
    """)

    # 12. New Modules D1 & D6: Safety Geofence & Rest Period Settings
    cur.execute("""
        CREATE TABLE IF NOT EXISTS safety_settings (
            id TEXT PRIMARY KEY,
            geofenceEnabled INTEGER NOT NULL DEFAULT 1,
            patientConsentGranted INTEGER NOT NULL DEFAULT 1,
            homeAddress TEXT NOT NULL,
            homeLat REAL NOT NULL,
            homeLng REAL NOT NULL,
            safeRadiusMeters REAL NOT NULL DEFAULT 350.0,
            currentLat REAL NOT NULL,
            currentLng REAL NOT NULL,
            sharingIntervalMins INTEGER NOT NULL DEFAULT 15,
            restPeriodStart TEXT NOT NULL DEFAULT '22:00',
            restPeriodEnd TEXT NOT NULL DEFAULT '06:30',
            suppressNonCriticalInRest INTEGER NOT NULL DEFAULT 1,
            updatedAt TEXT NOT NULL
        )
    """)

    # 13. Users & RBAC Permissions + Caregiver Audit Logs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            passwordHash TEXT NOT NULL,
            role TEXT NOT NULL,
            fullName TEXT NOT NULL,
            permissionsJson TEXT NOT NULL,
            createdAt TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            actorRole TEXT NOT NULL,
            actorName TEXT NOT NULL,
            action TEXT NOT NULL,
            resource TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            details TEXT
        )
    """)

    conn.commit()

    if force_reseed:
        for tbl in (
            "people",
            "places",
            "activities",
            "routines",
            "memories",
            "environment_guides",
            "emergency_contacts",
            "medications",
            "medication_logs",
            "reminders",
            "mood_checkins",
            "caregiver_notes",
            "safety_settings",
            "users",
            "audit_logs",
        ):
            cur.execute(f"DELETE FROM {tbl}")
        conn.commit()

    cur.execute("SELECT COUNT(*) as cnt FROM people")
    if cur.fetchone()["cnt"] == 0:
        seed_all_demo_data(conn)

    conn.close()


def seed_all_demo_data(conn: sqlite3.Connection):
    now = datetime.now()
    mins_ago = lambda m: (now - timedelta(minutes=m)).isoformat()
    days_ago = lambda d: (now - timedelta(days=d)).isoformat()
    cur = conn.cursor()

    # 1. Existing People (Preserved + enriched with photoCaption & voicePrompt for A1)
    people_rows = [
        (
            "per_ananya",
            "Ananya Sharma",
            "Teammate",
            "RNSIT College Hackathon Lab, Bengaluru",
            "college teammate, likes filter coffee, allergic to peanuts, builds RAG pipelines",
            "Birthday: Nov 12",
            None,
            "Ananya smiling at the RNSIT Hackathon table with a cup of filter coffee",
            "This is Ananya Sharma, your college teammate from RNSIT. Her birthday is November 12 and she loves South Indian filter coffee.",
            1,
            days_ago(1),
            days_ago(30),
        ),
        (
            "per_lakshmi",
            "Lakshmi Amma",
            "Family",
            "Home — Jayanagar 4th Block",
            "mother, takes Telma-40 BP tablet after breakfast, loves Carnatic flute concerts, keeps spare keys in brass bowl",
            "Birthday: Nov 22",
            None,
            "Lakshmi Amma in the Jayanagar garden wearing her green silk saree",
            "This is Lakshmi Amma, your mother at home in Jayanagar 4th Block. She loves Carnatic flute concerts.",
            1,
            mins_ago(45),
            days_ago(180),
        ),
        (
            "per_ramesh",
            "Dr. Ramesh Iyer",
            "Mentor",
            "IISc Open Day Symposium, Malleshwaram",
            "wears reading glasses, advises on API-key cloud LLM & RAG architecture, morning calls before 9 AM",
            "Work Anniversary: Sep 05",
            None,
            "Dr. Ramesh Iyer at the IISc Malleshwaram campus auditorium",
            "This is Dr. Ramesh Iyer, your project mentor from IISc Malleshwaram.",
            1,
            days_ago(4),
            days_ago(60),
        ),
        (
            "per_rahul",
            "Rahul Verma",
            "Colleague",
            "Bengaluru Tech Summit — Python Backend Track",
            "works on Python FastAPI & SQLite microservices, vegan, lives near Indiranagar Metro",
            "Birthday: Mar 03",
            None,
            "Rahul Verma presenting at Bengaluru Tech Summit",
            "This is Rahul Verma, your backend engineering colleague who lives near Indiranagar Metro.",
            1,
            days_ago(2),
            days_ago(15),
        ),
        (
            "per_priya",
            "Priya Nair",
            "Friend",
            "Cubbon Park Sunday Book Club",
            "family friend, collects fountain pens, allergic to dust, loves masala dosa at CTR Malleshwaram",
            "Birthday: Jan 19",
            None,
            "Priya Nair at the Cubbon Park bamboo grove book club",
            "This is Priya Nair, your close friend from the Cubbon Park Sunday Book Club.",
            1,
            days_ago(6),
            days_ago(90),
        ),
    ]
    cur.executemany(
        """
        INSERT INTO people (id, name, relationship, whereMet, keyFacts, importantDate, avatarUrl, photoCaption, voicePrompt, sharedWithCaregiver, lastInteraction, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        people_rows,
    )

    # 2. Existing Places & Items (Preserved including "Glasses on bedside table" for C6)
    places_rows = [
        (
            "plc_parking",
            "Bike parked",
            "Parking Spot",
            "Pillar B4 (Basement Level B2, Near Lift Lobby 2)",
            "White scooter KA-05-JM-4821 — parked at 09:15 AM",
            1,
            1,
            mins_ago(55),
            days_ago(1),
        ),
        (
            "plc_passport",
            "Passport",
            "Physical Item",
            "Top drawer in study room",
            "Inside blue zippered fireproof folder alongside Aadhaar card",
            1,
            1,
            days_ago(3),
            days_ago(30),
        ),
        (
            "plc_glasses",
            "Reading Glasses",
            "Physical Item",
            "On the bedside table next to the brass lamp",
            "Silver-rimmed reading glasses in brown leather case",
            1,
            1,
            mins_ago(25),
            days_ago(10),
        ),
        (
            "plc_keys",
            "Spare House & Gate Keys",
            "Physical Item",
            "Inside the blue Wildcraft backpack front zip pocket",
            "Has a yellow reflective keychain tag",
            1,
            1,
            days_ago(1),
            days_ago(14),
        ),
        (
            "plc_clinic",
            "Family Clinic — Dr. Mehta Diagnostics",
            "Important Address",
            "11th Main Road, 4th Block Jayanagar, Opposite Cool Joint",
            "Navigation note: Enter via 10th Cross side street; pharmacy 24x7",
            0,
            1,
            days_ago(12),
            days_ago(60),
        ),
    ]
    cur.executemany(
        """
        INSERT INTO places (id, title, category, exactLocation, notes, isPinned, sharedWithCaregiver, updatedAt, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        places_rows,
    )

    # 3. Existing Daily Activities (Preserved)
    activities_rows = [
        ("act_1", "Drank water", "Health/Meds", "500ml warm water after morning walk", "voice", mins_ago(18)),
        ("act_2", "Locked main door", "Home Security", "Double-checked safety latch and gas cylinder valve", "quick-tap", mins_ago(65)),
        ("act_3", "Took morning vitamin", "Health/Meds", "Vitamin D3 & B12 after idli breakfast", "quick-tap", mins_ago(115)),
        ("act_4", "Paid electricity bill", "Bills/Errands", "BESCOM bill ₹1,840 paid via UPI AutoPay", "manual", mins_ago(190)),
    ]
    cur.executemany(
        "INSERT INTO activities (id, actionTitle, category, notes, source, loggedAt) VALUES (?, ?, ?, ?, ?, ?)",
        activities_rows,
    )

    # 4. Existing Routines (Preserved)
    routines_rows = [
        ("rtn_1", "Morning Thyroid & BP Medication", "08:00 AM", "Daily", "CRITICAL", 1, 1, mins_ago(135), 18, days_ago(30)),
        ("rtn_2", "Morning Routine — Check Gas Stove & Main Door Lock", "09:00 AM", "Daily", "CRITICAL", 1, 0, days_ago(1), 12, days_ago(30)),
        ("rtn_3", "Evening Gym Session & Strength Workout", "06:30 PM", "Weekdays", "NORMAL", 0, 0, days_ago(1), 9, days_ago(20)),
        ("rtn_4", "Night Study Block — System Design & Cloud AI RAG", "08:30 PM", "Weekdays", "NORMAL", 0, 0, days_ago(1), 14, days_ago(25)),
        ("rtn_5", "Bill Due Date — Electricity & Monthly House Rent", "10:00 AM", "Custom Days", "CRITICAL", 1, 1, mins_ago(190), 6, days_ago(60)),
    ]
    cur.executemany(
        """
        INSERT INTO routines (id, title, timeSlot, frequency, priority, shareWithCircle, completedToday, lastCompletedAt, streakCount, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        routines_rows,
    )

    # 5. Module A3: Personal Life Story & Memory Album
    memories_rows = [
        (
            "mem_1",
            "Summer Holidays at Mysuru Ancestral Home",
            "Childhood Memory",
            "Every May we took the morning train to Mysuru, ate fresh mangoes in the courtyard, and listened to grandfather's radio stories on the verandah.",
            "1978",
            None,
            "M.S. Subbulakshmi — Suprabhatam",
            "Lakshmi Amma, Grandfather",
            1,
            days_ago(40),
        ),
        (
            "mem_2",
            "Golden Jubilee Family Reunion at Lalbagh Glass House",
            "Family Occasion",
            "The whole family gathered at Lalbagh Botanical Garden on a sunny Sunday morning, followed by a traditional South Indian banana-leaf lunch at Mavalli Tiffin Room (MTR).",
            "2019",
            None,
            "Carnatic Flute — Raaga Hamsadhwani by T.R. Mahalingam",
            "Lakshmi Amma, Ananya Sharma, Priya Nair",
            1,
            days_ago(20),
        ),
        (
            "mem_3",
            "First Engineering Project Award & Distinguished Service Medal",
            "Personal Achievement",
            "Received the Best Systems Engineering Award in Bengaluru with family cheering from the front row.",
            "2005",
            None,
            "Veena Instrumental — Vatapi Ganapatim",
            "Lakshmi Amma, Dr. Ramesh Iyer",
            1,
            days_ago(15),
        ),
    ]
    cur.executemany(
        """
        INSERT INTO memories (id, title, category, storyText, eraOrYear, mediaUrl, favouriteMusic, involvedPeople, sharedWithCaregiver, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        memories_rows,
    )

    # 6. Module A4: Familiar Environment Guide
    env_guides = [
        (
            "env_1",
            "Bathroom",
            "🚿",
            "Bathroom is on the left past the bedroom wooden door. The light switch is outside on the right wall.",
            "The bathroom is on your left, just past the bedroom door. The light switch is on the right side of the doorframe.",
            "Home Indoor",
            1,
            now.isoformat(),
        ),
        (
            "env_2",
            "Bedroom",
            "🛏️",
            "Bedroom is upstairs at the end of the hallway, first door on the right with the brass nameplate.",
            "Your bedroom is upstairs at the end of the hall, the first door on the right.",
            "Home Indoor",
            1,
            now.isoformat(),
        ),
        (
            "env_3",
            "Drinking Water",
            "💧",
            "Drinking water is in the kitchen on the granite counter next to the copper pot and steel tumblers.",
            "Warm drinking water is in the kitchen on the counter, right inside the copper vessel.",
            "Kitchen",
            1,
            now.isoformat(),
        ),
        (
            "env_4",
            "Walking Shoes",
            "👟",
            "Walking shoes are near the main entrance on the bottom shelf of the bamboo shoe rack.",
            "Your comfortable walking shoes are near the front entrance on the bottom shelf of the shoe rack.",
            "Entrance",
            1,
            now.isoformat(),
        ),
    ]
    cur.executemany(
        """
        INSERT INTO environment_guides (id, locationName, visualIcon, stepByStepInstruction, spokenPrompt, roomCategory, isPinned, updatedAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        env_guides,
    )

    # 7. Module A5: Emergency SOS Contacts
    sos_rows = [
        (
            "sos_1",
            "Lakshmi Amma (Primary Family Caregiver)",
            "Family / Mother",
            "+91-98450-11223",
            1,
            "#42, 11th Main Road, Jayanagar 4th Block, Bengaluru 560011",
            "Blood Group: O+ | Allergy: Peanuts & Dust | Regular Med: Telma-40 (Morning 8:00 AM)",
        ),
        (
            "sos_2",
            "Ananya Sharma (Emergency Family/Teammate Contact)",
            "Daughter / Care Circle",
            "+91-99001-44556",
            0,
            "#42, 11th Main Road, Jayanagar 4th Block, Bengaluru 560011",
            "Lives 10 mins away; holds spare house key",
        ),
        (
            "sos_3",
            "Dr. Mehta Family Clinic & 24x7 Ambulance Desk",
            "Doctor / Medical Emergency",
            "108",
            0,
            "11th Main Road, Jayanagar 4th Block (Opposite Cool Joint)",
            "Patient ID: JYN-4092",
        ),
    ]
    cur.executemany(
        """
        INSERT INTO emergency_contacts (id, name, relationship, phone, isPrimary, homeAddress, medicalNotes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        sos_rows,
    )

    # 8. Module A6: Medication Schedules & Logs
    med_rows = [
        (
            "med_1",
            "Telma-40 (BP Tablet)",
            "40 mg — 1 Tablet",
            "08:00 AM",
            "Take after morning breakfast with warm water",
            1,
            1,
            "TAKEN",
            mins_ago(135),
            None,
            days_ago(30),
        ),
        (
            "med_2",
            "Vitamin D3 & B12 Neuro Supplement",
            "1 Capsule",
            "01:30 PM",
            "Take after lunch (Stored in white medical box on dining shelf)",
            0,
            1,
            "PENDING",
            None,
            None,
            days_ago(30),
        ),
        (
            "med_3",
            "Evening Memantine / Memory Care Dose",
            "10 mg — 1 Tablet",
            "08:00 PM",
            "Critical evening dose — must be confirmed after dinner",
            1,
            1,
            "PENDING",
            None,
            None,
            days_ago(30),
        ),
    ]
    cur.executemany(
        """
        INSERT INTO medications (id, medicationName, dosageDisplay, scheduledTime, instructions, isCritical, shareWithCaregiver, status, lastConfirmedAt, snoozedUntil, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        med_rows,
    )

    cur.execute(
        """
        INSERT INTO medication_logs (id, medicationId, medicationName, action, confirmedBy, timestamp, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "mlog_1",
            "med_1",
            "Telma-40 (BP Tablet)",
            "TAKEN",
            "Patient Confirmation",
            mins_ago(135),
            "Confirmed via Morning Medication Card",
        ),
    )

    # 9. Module B: Persistent Vibration & Acknowledgement Reminders
    reminder_rows = [
        (
            "rem_1",
            "08:00 AM — Morning Telma-40 Medication & Warm Water",
            "Medication",
            "08:00 AM",
            "Critical",
            120,
            5,
            30,
            "ACKNOWLEDGED",
            mins_ago(135),
            None,
            0,
            1,
            days_ago(10),
        ),
        (
            "rem_2",
            "09:00 AM — Lock Main Wooden Door & Check Gas Stove Knob",
            "Home Safety",
            "09:00 AM",
            "Critical",
            120,
            5,
            30,
            "ACTIVE",
            None,
            None,
            2,
            1,
            days_ago(10),
        ),
        (
            "rem_3",
            "04:30 PM — Afternoon Filter Coffee & Hydration Break",
            "Hydration",
            "04:30 PM",
            "Normal",
            180,
            10,
            60,
            "ACTIVE",
            None,
            None,
            0,
            1,
            days_ago(5),
        ),
    ]
    cur.executemany(
        """
        INSERT INTO reminders (id, title, category, scheduledTime, priority, repeatIntervalSec, snoozeDurationMins, escalationWindowMins, status, acknowledgedAt, snoozedUntil, retryCount, shareWithCaregiver, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        reminder_rows,
    )

    # 10. Module D3: Mood Check-ins
    mood_rows = [
        ("mood_1", "Happy", "Enjoyed listening to Carnatic flute music this morning", 1, mins_ago(90)),
        ("mood_2", "Normal", "Quiet afternoon reading after lunch", 1, days_ago(1)),
    ]
    cur.executemany(
        "INSERT INTO mood_checkins (id, mood, notes, sharedWithCaregiver, loggedAt) VALUES (?, ?, ?, ?, ?)",
        mood_rows,
    )

    # 11. Module D4: Caregiver Notes, Appointments & Expected Visits
    cg_notes = [
        (
            "cgn_1",
            "Lakshmi Amma (Caregiver)",
            "Expected Visit",
            "Ananya Visiting for Evening Filter Coffee",
            "Ananya will visit around 5:30 PM today bringing fresh filter coffee powder from Jayanagar.",
            "Today, 05:30 PM",
            mins_ago(120),
        ),
        (
            "cgn_2",
            "Dr. Mehta Clinic",
            "Appointment",
            "Routine Blood Pressure & Memory Checkup",
            "Bring previous prescription folder from the study room top drawer.",
            "Tomorrow, 10:30 AM",
            days_ago(1),
        ),
        (
            "cgn_3",
            "Lakshmi Amma (Caregiver)",
            "Observation",
            "Morning Hydration & Glasses Placement",
            "Patient kept reading glasses on the bedside table next to the brass lamp.",
            "Today",
            mins_ago(60),
        ),
    ]
    cur.executemany(
        """
        INSERT INTO caregiver_notes (id, authorName, noteType, title, content, scheduledFor, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        cg_notes,
    )

    # 12. Modules D1 & D6: Safety Geofence & Rest Period Settings
    cur.execute(
        """
        INSERT INTO safety_settings (
            id, geofenceEnabled, patientConsentGranted, homeAddress,
            homeLat, homeLng, safeRadiusMeters, currentLat, currentLng,
            sharingIntervalMins, restPeriodStart, restPeriodEnd, suppressNonCriticalInRest, updatedAt
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "safe_default",
            1,
            1,
            "#42, 11th Main Road, Jayanagar 4th Block, Bengaluru 560011",
            12.9299,
            77.5824,
            350.0,
            12.9304,
            77.5828,
            15,
            "22:00",
            "06:30",
            1,
            now.isoformat(),
        ),
    )

    # 13. Users & Selective Caregiver Permissions
    default_perms = json.dumps(
        {
            "canViewPeople": True,
            "canViewMemories": True,
            "canViewMedications": True,
            "canViewLocation": True,
            "canManageRoutines": True,
        }
    )
    users_rows = [
        ("usr_patient", "patient", hash_password("patient123"), "patient", "Adithiyha / Primary User", default_perms, days_ago(60)),
        ("usr_caregiver", "caregiver", hash_password("care123"), "caregiver", "Lakshmi Amma (Authorized Caregiver)", default_perms, days_ago(60)),
    ]
    cur.executemany(
        "INSERT INTO users (id, username, passwordHash, role, fullName, permissionsJson, createdAt) VALUES (?, ?, ?, ?, ?, ?, ?)",
        users_rows,
    )

    cur.execute(
        "INSERT INTO audit_logs (id, actorRole, actorName, action, resource, timestamp, details) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "aud_1",
            "caregiver",
            "Lakshmi Amma",
            "VIEW_DASHBOARD",
            "/api/caregivers/dashboard",
            mins_ago(30),
            "Reviewed morning medication confirmation and added 5:30 PM expected visit note.",
        ),
    )

    conn.commit()
