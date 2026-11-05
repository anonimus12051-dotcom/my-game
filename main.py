from fastapi.responses import FileResponse
import os
import hmac
import hashlib
import json
import time

from urllib.parse import parse_qsl
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client

app = FastAPI(title="My Game API")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not SUPABASE_URL or not SUPABASE_KEY or not BOT_TOKEN:
    raise RuntimeError("Missing environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

CLASSES = ("fighter", "rogue", "gatherer")
PLAYER_FIELDS = (
    "telegram_id,username,first_name,photo_url,"
    "balance,level,xp,hp,class,stat_points"
)


class TelegramAuthRequest(BaseModel):
    init_data: str


class ClassRequest(BaseModel):
    init_data: str
    player_class: str


def verify_telegram_data(init_data: str):
    data = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = data.pop("hash", None)

    if not received_hash:
        raise HTTPException(401, "Missing Telegram hash")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(data.items())
    )

    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
    ).digest()

    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(401, "Invalid Telegram data")

    try:
        auth_date = int(data["auth_date"])

        if time.time() - auth_date > 86400 or auth_date > time.time() + 60:
            raise HTTPException(401, "Telegram data expired")

        user = json.loads(data["user"])

        if not isinstance(user, dict) or not user.get("id"):
            raise ValueError()

        return user

    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(401, "Invalid Telegram user data")


def load_player(telegram_id: int):
    result = (
        supabase.table("players")
        .select(PLAYER_FIELDS)
        .eq("telegram_id", telegram_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Player not found")

    player = result.data[0]
    player["xp_to_next"] = player["level"] * 100
    return player


@app.get("/")
def home():
    return FileResponse("static/index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/db-check")
def db_check():
    try:
        supabase.table("players").select("id").limit(1).execute()
        return {
            "status": "connected",
            "database": "online",
            "players_table": "found",
        }
    except Exception:
        return {"status": "error", "database": "connection failed"}


@app.post("/auth/telegram")
def telegram_auth(request: TelegramAuthRequest):
    user = verify_telegram_data(request.init_data)

    player_data = {
        "telegram_id": user["id"],
        "username": user.get("username"),
        "first_name": user.get("first_name", ""),
        "photo_url": user.get("photo_url"),
    }

    try:
        supabase.table("players").upsert(
            player_data, on_conflict="telegram_id"
        ).execute()
        player = load_player(user["id"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Database error")

    return {"status": "success", "player": player}


@app.post("/profile/class")
def set_class(request: ClassRequest):
    user = verify_telegram_data(request.init_data)

    if request.player_class not in CLASSES:
        raise HTTPException(400, "Unknown class")

    try:
        supabase.table("players").update(
            {"class": request.player_class}
        ).eq("telegram_id", user["id"]).execute()
        player = load_player(user["id"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Database error")

    return {"status": "success", "player": player}
