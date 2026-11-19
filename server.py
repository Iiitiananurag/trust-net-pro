import os
import subprocess
import uvicorn

from engine.db import init_db

if not os.path.exists("trustnet.db"):
    init_db()
    subprocess.run(["python", "-m", "simulator.seed"], check=False)

from main import app  # ← FIXED: points to main.py now

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
