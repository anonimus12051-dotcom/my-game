import os

from fastapi import FastAPI
from supabase import create_client, Client

app = FastAPI(title="My Game API")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


@app.get("/")
def home():
    return {
        "status": "online",
        "message": "Game server is working!"
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/db-check")
def db_check():
    try:
        result = supabase.table("players").select("id").limit(1).execute()

        return {
            "status": "connected",
            "database": "online",
            "players_table": "found"
        }

    except Exception:
        return {
            "status": "error",
            "database": "connection failed"
        }
