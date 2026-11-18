"""
MEMOSPHERE Main Application Entrypoint
Your Personal AI Memory Companion — "Never Lose a Memory. Never Feel Alone."
Initializes Flask, SQLite/SQLAlchemy, Flask-CORS, APScheduler, and all REST & Frontend routes.
"""
import os
from pathlib import Path
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS

from config import Config
from backend.models import (
    db,
    User,
    Memory,
    Reminder,
    RoutineLog,
    Conversation,
    CaregiverPermission,
    utc_now,
)
from backend.routes.auth import auth_bp
from backend.routes.memories import memories_bp
from backend.routes.assistant import assistant_bp
from backend.routes.reminders import reminders_bp
from backend.routes.routines import routines_bp
from backend.routes.caregiver import caregiver_bp
from backend.routes.ai_settings import ai_settings_bp
from backend.services.reminder_service import ReminderService

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"


def seed_initial_data() -> None:
    """Seed helpful initial demo data if the SQLite database is empty."""
    if User.query.first() is not None:
        return

    # 1. Primary user & Caregiver user
    primary_user = User(name="Aarav Sharma", email="aarav@memosphere.local", role="user")
    primary_user.set_password("memosphere123")
    db.session.add(primary_user)

    caregiver = User(name="Priya Sharma (Caregiver)", email="priya@memosphere.local", role="caregiver")
    caregiver.set_password("caregiver123")
    db.session.add(caregiver)
    db.session.commit()

    # 2. Explicit Caregiver Consent Permission
    consent = CaregiverPermission(
        user_id=primary_user.id,
        caregiver_id=caregiver.id,
        permission_type="routines_and_reminders",
        consent_status="granted",
    )
    db.session.add(consent)

    # 3. Sample Memories across all 5 categories (People, Places, Items, Activities, Routines)
    sample_memories = [
        Memory(
            user_id=primary_user.id,
            category="Items",
            title="Phone Charger Location",
            content="Charger is in the blue bag near the study desk.",
            entity_name="Charger",
            location="Blue bag",
            event_date="2026-11-17",
        ),
        Memory(
            user_id=primary_user.id,
            category="Items",
            title="House Keys Location",
            content="Kept my house keys in the ceramic bowl on the entryway table.",
            entity_name="House keys",
            location="Ceramic bowl on entryway table",
            event_date="2026-11-18",
        ),
        Memory(
            user_id=primary_user.id,
            category="Items",
            title="Reading Glasses",
            content="Reading glasses are inside the top drawer of the bedside table.",
            entity_name="Reading glasses",
            location="Top drawer of bedside table",
            event_date="2026-11-18",
        ),
        Memory(
            user_id=primary_user.id,
            category="People",
            title="Met Rahul",
            content="Met Rahul at the community pottery workshop yesterday. He shared gardening tips.",
            entity_name="Rahul",
            location="Community Workshop",
            event_date="2026-11-17",
        ),
        Memory(
            user_id=primary_user.id,
            category="People",
            title="Dr. Meera Nair Appointment Note",
            content="Dr. Meera Nair (Cardiologist) advised continuing the 20-minute evening walk and low-sodium diet.",
            entity_name="Dr. Meera Nair",
            location="Sunrise Clinic",
            event_date="2026-11-15",
        ),
        Memory(
            user_id=primary_user.id,
            category="Places",
            title="Greenfield Botanical Park",
            content="Visited Greenfield Botanical Park via the East Gate bench trail; very peaceful in the mornings.",
            entity_name="Greenfield Botanical Park",
            location="East Gate Bench Trail",
            event_date="2026-11-16",
        ),
        Memory(
            user_id=primary_user.id,
            category="Activities",
            title="Completed Evening Walk",
            content="Completed my evening walk at 7:30 PM around the neighborhood park.",
            entity_name="Evening walk",
            location="Neighborhood Park",
            event_date="2026-11-17",
        ),
        Memory(
            user_id=primary_user.id,
            category="Routines",
            title="Morning Vitamin D & Blood Pressure Pill",
            content="Take Vitamin D and Amlodipine 5mg every morning at 8:30 AM after breakfast.",
            entity_name="Morning Medication",
            location="Kitchen medicine organizer",
            event_date="2026-11-18",
        ),
    ]
    for mem in sample_memories:
        db.session.add(mem)

    # 4. Sample Reminders with Friendly, Calm, and Direct tones
    sample_reminders = [
        Reminder(
            user_id=primary_user.id,
            title="Evening Walk",
            description="20-minute gentle walk around the park",
            reminder_datetime="7:30 PM",
            recurrence="daily",
            tone="Friendly",
            completed=False,
        ),
        Reminder(
            user_id=primary_user.id,
            title="Afternoon Hydration & Fruit",
            description="Drink a full glass of water and have seasonal fruit",
            reminder_datetime="4:00 PM",
            recurrence="daily",
            tone="Calm",
            completed=False,
        ),
        Reminder(
            user_id=primary_user.id,
            title="Morning Blood Pressure Medication",
            description="Amlodipine 5mg after breakfast",
            reminder_datetime="8:30 AM",
            recurrence="daily",
            tone="Direct",
            completed=True,
        ),
    ]
    for rem in sample_reminders:
        db.session.add(rem)

    # 5. Sample Routine Logs (including completed, pending, and missed for Caregiver insights)
    sample_routines = [
        RoutineLog(
            user_id=primary_user.id,
            routine_name="Morning Blood Pressure & Vitamin D",
            completion_status="completed",
            scheduled_time="08:30 AM",
            completed_at=utc_now(),
        ),
        RoutineLog(
            user_id=primary_user.id,
            routine_name="15-Minute Brain & Memory Puzzle",
            completion_status="completed",
            scheduled_time="10:30 AM",
            completed_at=utc_now(),
        ),
        RoutineLog(
            user_id=primary_user.id,
            routine_name="Midday Hydration Check",
            completion_status="missed",
            scheduled_time="01:30 PM",
            completed_at=None,
        ),
        RoutineLog(
            user_id=primary_user.id,
            routine_name="Afternoon Stretching",
            completion_status="missed",
            scheduled_time="04:30 PM",
            completed_at=None,
        ),
        RoutineLog(
            user_id=primary_user.id,
            routine_name="Evening Walk (20 mins)",
            completion_status="pending",
            scheduled_time="07:30 PM",
            completed_at=None,
        ),
    ]
    for rout in sample_routines:
        db.session.add(rout)

    # 6. Initial Conversation sample
    conv = Conversation(
        user_id=primary_user.id,
        question="Where did I keep my charger?",
        answer="You saved that your charger is in the blue bag near the study desk.",
    )
    db.session.add(conv)
    db.session.commit()


def create_app(test_config: dict | None = None) -> Flask:
    """Application factory for MEMOSPHERE."""
    app = Flask(
        __name__,
        static_folder=str(FRONTEND_DIR),
        static_url_path="",
    )
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["SQLALCHEMY_DATABASE_URI"] = Config.SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if test_config:
        app.config.update(test_config)

    CORS(app, supports_credentials=True)
    db.init_app(app)

    # Register API blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(memories_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(reminders_bp)
    app.register_blueprint(routines_bp)
    app.register_blueprint(caregiver_bp)
    app.register_blueprint(ai_settings_bp)

    # Frontend page routes
    @app.route("/", methods=["GET"])
    def serve_index():
        return send_from_directory(str(FRONTEND_DIR), "index.html")

    @app.route("/index.html", methods=["GET"])
    def serve_index_explicit():
        return send_from_directory(str(FRONTEND_DIR), "index.html")

    @app.route("/login", methods=["GET"])
    @app.route("/login.html", methods=["GET"])
    def serve_login():
        return send_from_directory(str(FRONTEND_DIR), "login.html")

    @app.route("/caregiver", methods=["GET"])
    @app.route("/caregiver.html", methods=["GET"])
    def serve_caregiver():
        return send_from_directory(str(FRONTEND_DIR), "caregiver.html")

    @app.route("/settings", methods=["GET"])
    @app.route("/settings.html", methods=["GET"])
    def serve_settings():
        return send_from_directory(str(FRONTEND_DIR), "settings.html")

    @app.route("/css/<path:filename>", methods=["GET"])
    def serve_css(filename: str):
        return send_from_directory(str(FRONTEND_DIR / "css"), filename)

    @app.route("/js/<path:filename>", methods=["GET"])
    def serve_js(filename: str):
        return send_from_directory(str(FRONTEND_DIR / "js"), filename)

    @app.route("/assets/<path:filename>", methods=["GET"])
    def serve_assets(filename: str):
        return send_from_directory(str(FRONTEND_DIR / "assets"), filename)

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "app": "MEMOSPHERE"}), 200

    with app.app_context():
        db.create_all()
        if not app.config.get("TESTING", False):
            seed_initial_data()
        ReminderService.init_scheduler(app)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=Config.PORT, debug=Config.DEBUG)
