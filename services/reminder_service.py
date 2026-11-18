import re
from datetime import datetime
from database import get_db_connection


def time_str_to_minutes(t_str: str) -> int:
    s = (t_str or "").strip()
    m12 = re.match(r"^(\d{1,2}):(\d{2})\s*(AM|PM)$", s, re.IGNORECASE)
    if m12:
        h = int(m12.group(1))
        m = int(m12.group(2))
        p = m12.group(3).upper()
        if p == "PM" and h < 12:
            h += 12
        if p == "AM" and h == 12:
            h = 0
        return h * 60 + m
    m24 = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m24:
        return int(m24.group(1)) * 60 + int(m24.group(2))
    return 12 * 60


def is_within_rest_period(current_mins: int, start_str: str, end_str: str) -> bool:
    start_m = time_str_to_minutes(start_str)
    end_m = time_str_to_minutes(end_str)
    if start_m <= end_m:
        return start_m <= current_mins <= end_m
    # Overnight rest period (e.g., 22:00 to 06:30)
    return current_mins >= start_m or current_mins <= end_m


def evaluate_reminders_and_escalations() -> dict:
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM safety_settings LIMIT 1")
    safety = dict(cur.fetchone() or {})
    rest_start = safety.get("restPeriodStart", "22:00")
    rest_end = safety.get("restPeriodEnd", "06:30")
    suppress_non_crit = bool(safety.get("suppressNonCriticalInRest", 1))

    now = datetime.now()
    current_mins = now.hour * 60 + now.minute
    in_rest = is_within_rest_period(current_mins, rest_start, rest_end)

    cur.execute("SELECT * FROM reminders ORDER BY scheduledTime ASC")
    reminders = [dict(r) for r in cur.fetchall()]
    conn.close()

    due_for_vibration = []
    escalated_to_caregiver = []

    for r in reminders:
        sched_m = time_str_to_minutes(r["scheduledTime"])
        elapsed_mins = current_mins - sched_m

        if r["status"] == "ACKNOWLEDGED":
            continue

        # Suppress non-critical reminders during Rest Period (D6)
        if in_rest and suppress_non_crit and r["priority"] != "Critical":
            r["suppressedByRestPeriod"] = True
            continue

        r["suppressedByRestPeriod"] = False
        if elapsed_mins >= 0:
            due_for_vibration.append(r)
            if r["priority"] == "Critical" and elapsed_mins >= int(r["escalationWindowMins"]):
                escalated_to_caregiver.append(r)

    return {
        "evaluatedAt": now.isoformat(),
        "inRestPeriod": in_rest,
        "restWindow": f"{rest_start} – {rest_end}",
        "activeDueCount": len(due_for_vibration),
        "escalatedCount": len(escalated_to_caregiver),
        "dueReminders": due_for_vibration,
        "escalatedReminders": escalated_to_caregiver,
        "allReminders": reminders,
    }
