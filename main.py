import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from database import init_db
from routers import (
    authentication,
    people,
    places,
    memories,
    activities,
    routines,
    medication,
    reminders,
    voice,
    ai,
    caregivers,
    safety,
    reports,
)

init_db(force_reseed=False)

app = FastAPI(
    title="Memosphere — AI Personal Memory & Dementia Care Companion API",
    version="2.0.0",
    description="Local-first SQLite Personal Knowledge Base + Dementia Care Companion with Backend-Only Cloud AI Integration",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all modular routers
app.include_router(authentication.router)
app.include_router(people.router)
app.include_router(places.router)
app.include_router(memories.router)
app.include_router(activities.router)
app.include_router(routines.router)
app.include_router(medication.router)
app.include_router(reminders.router)
app.include_router(voice.router)
app.include_router(ai.router)
app.include_router(caregivers.router)
app.include_router(safety.router)
app.include_router(reports.router)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@app.get("/")
def serve_home():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/manifest.json")
def serve_manifest():
    return FileResponse(os.path.join(FRONTEND_DIR, "manifest.json"))


@app.get("/service-worker.js")
def serve_sw():
    return FileResponse(os.path.join(FRONTEND_DIR, "service-worker.js"))


if os.path.exists(os.path.join(FRONTEND_DIR, "css")):
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
if os.path.exists(os.path.join(FRONTEND_DIR, "js")):
    app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")
