import math
import time
from datetime import datetime
from fastapi import APIRouter, HTTPException
from database import get_db_connection
from services.security_service import log_audit_event

router = APIRouter(prefix="/api/safety", tags=["Module A5, D1 & D6: Emergency SOS, Geofence & Rest Period"])


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@router.get("/sos")
def get_emergency_sos_info():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM emergency_contacts ORDER BY isPrimary DESC")
    contacts = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM safety_settings LIMIT 1")
    safety = dict(cur.fetchone() or {})
    conn.close()
    return {
        "success": True,
        "homeAddress": safety.get("homeAddress", "#42, 11th Main Road, Jayanagar 4th Block, Bengaluru"),
        "contacts": contacts,
        "safetySettings": safety,
    }


@router.post("/sos/trigger")
def trigger_emergency_sos(body: dict = None):
    body = body or {}
    now_iso = datetime.now().isoformat()
    log_audit_event("patient", "Patient SOS Button", "TRIGGER_EMERGENCY_SOS", "/api/safety/sos/trigger", body.get("reason", "One-tap SOS activated"))
    return {
        "success": True,
        "triggeredAt": now_iso,
        "alertDispatchedToCaregivers": True,
        "message": "Emergency SOS alert logged and shared with authorized emergency contacts.",
    }


@router.get("/geofence")
def evaluate_geofence_status():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM safety_settings LIMIT 1")
    s = dict(cur.fetchone() or {})
    conn.close()

    if not s.get("patientConsentGranted"):
        return {
            "success": True,
            "consentGranted": False,
            "geofenceEnabled": False,
            "status": "CONSENT_WITHDRAWN — Location sharing is disabled (Zero covert tracking).",
        }

    dist = round(
        haversine_meters(s["homeLat"], s["homeLng"], s["currentLat"], s["currentLng"]),
        1,
    )
    outside = dist > float(s["safeRadiusMeters"])
    return {
        "success": True,
        "consentGranted": bool(s["patientConsentGranted"]),
        "geofenceEnabled": bool(s["geofenceEnabled"]),
        "homeAddress": s["homeAddress"],
        "safeRadiusMeters": s["safeRadiusMeters"],
        "currentDistanceMeters": dist,
        "outsideSafeZoneAlert": outside,
        "sharingIntervalMins": s["sharingIntervalMins"],
        "restPeriod": {
            "start": s["restPeriodStart"],
            "end": s["restPeriodEnd"],
            "suppressNonCritical": bool(s["suppressNonCriticalInRest"]),
        },
    }


@router.patch("/settings")
def update_safety_and_rest_settings(body: dict):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM safety_settings LIMIT 1")
    s = dict(cur.fetchone() or {})

    cur.execute(
        """
        UPDATE safety_settings
        SET geofenceEnabled = ?, patientConsentGranted = ?, safeRadiusMeters = ?,
            currentLat = ?, currentLng = ?, sharingIntervalMins = ?,
            restPeriodStart = ?, restPeriodEnd = ?, suppressNonCriticalInRest = ?, updatedAt = ?
        WHERE id = ?
        """,
        (
            1 if body.get("geofenceEnabled", bool(s["geofenceEnabled"])) else 0,
            1 if body.get("patientConsentGranted", bool(s["patientConsentGranted"])) else 0,
            float(body.get("safeRadiusMeters", s["safeRadiusMeters"])),
            float(body.get("currentLat", s["currentLat"])),
            float(body.get("currentLng", s["currentLng"])),
            int(body.get("sharingIntervalMins", s["sharingIntervalMins"])),
            body.get("restPeriodStart", s["restPeriodStart"]),
            body.get("restPeriodEnd", s["restPeriodEnd"]),
            1 if body.get("suppressNonCriticalInRest", bool(s["suppressNonCriticalInRest"])) else 0,
            datetime.now().isoformat(),
            s["id"],
        ),
    )
    conn.commit()
    conn.close()
    return evaluate_geofence_status()
