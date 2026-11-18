import uvicorn
from config import settings

if __name__ == "__main__":
    print(f"Starting Memosphere FastAPI Server at http://localhost:{settings.port}")
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
