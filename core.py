import functools
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl

from fastapi import HTTPException
from pydantic import BaseModel
from supabase import Client, create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not SUPABASE_URL or not SUPABASE_KEY or not BOT_TOKEN:
    raise RuntimeError("Missing environment variables")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

INVENTORY_SIZE = 10


class InitRequest(BaseModel):
    init_data: str


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


def user_id(init_data: str) -> int:
    return verify_telegram_data(init_data)["id"]


def safe(fn):
    """Превращает неожиданные ошибки в ответ 500 и пишет их в логи Render."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as e:
            print("ERROR in", fn.__name__, ":", repr(e))
            raise HTTPException(500, "Database error")
    return wrapper


def change_balance(telegram_id: int, delta: int):
    """Безопасно меняет серебро. Не даёт уйти в минус."""
    for _ in range(5):
        result = (
            supabase.table("players")
            .select("balance")
            .eq("telegram_id", telegram_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            raise HTTPException(404, "Player not found")

        old = result.data[0]["balance"]
        new = old + delta

        if new < 0:
            raise HTTPException(400, "Не хватает серебра")

        updated = (
            supabase.table("players")
            .update({"balance": new})
            .eq("telegram_id", telegram_id)
            .eq("balance", old)
            .execute()
        )
        if updated.data:
            return new

    raise HTTPException(409, "Попробуй ещё раз")


# ---------- сессии: где сейчас игрок (лес, озеро, бой) ----------

def start_session(tid: int, kind: str, data: dict):
    supabase.table("sessions").upsert(
        {"telegram_id": tid, "kind": kind, "data": data, "ver": 0},
        on_conflict="telegram_id",
    ).execute()


def load_session(tid: int, kind: str):
    r = (
        supabase.table("sessions")
        .select("kind,data,ver")
        .eq("telegram_id", tid)
        .limit(1)
        .execute()
    )
    if not r.data or r.data[0]["kind"] != kind:
        raise HTTPException(400, "Ты сейчас не здесь")
    return r.data[0]["data"], r.data[0]["ver"]


def commit_session(tid: int, data: dict, ver: int):
    """Сохраняет, только если сессию никто не менял (защита от двойных нажатий)."""
    ok = (
        supabase.table("sessions")
        .update({"data": data, "ver": ver + 1})
        .eq("telegram_id", tid)
        .eq("ver", ver)
        .execute()
    )
    if not ok.data:
        raise HTTPException(409, "Слишком быстро, попробуй ещё раз")


def clear_session(tid: int):
    supabase.table("sessions").delete().eq("telegram_id", tid).execute()
