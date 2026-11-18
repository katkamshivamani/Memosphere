from database import init_db

if __name__ == "__main__":
    print("🌱 Resetting and seeding Memosphere SQLite database...")
    init_db(force_reseed=True)
    print("🎉 Done! Run `python app.py` to start the server.")
