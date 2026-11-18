from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.security_service import (
    authenticate_user,
    get_caregiver_permissions,
    update_caregiver_permissions,
    log_audit_event,
)

router = APIRouter(prefix="/api/auth", tags=["Authentication & Authorization"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(payload: LoginRequest):
    auth = authenticate_user(payload.username, payload.password)
    if not auth:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    log_audit_event(auth["user"]["role"], auth["user"]["fullName"], "LOGIN", "/api/auth/login")
    return {"success": True, **auth}


@router.get("/permissions")
def get_permissions():
    return {"success": True, "permissions": get_caregiver_permissions()}


@router.patch("/permissions")
def patch_permissions(payload: dict):
    updated = update_caregiver_permissions(payload)
    return {"success": True, "permissions": updated}
