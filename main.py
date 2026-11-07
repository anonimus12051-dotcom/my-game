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
SHOP_CATEGORIES = ["pvp", "mine", "other"]
INVENTORY_SIZE = 10
STARTER_ITEMS = ["wooden_sword", "leather_helmet", "bandage", "bandage"]
PLAYER_FIELDS = (
    "telegram_id,username,first_name,photo_url,"
    "balance,level,xp,hp,class,stat_points"
)


class TelegramAuthRequest(BaseModel):
    init_data: str


class ClassRequest(BaseModel):
    init_data: str
    player_class: str


class ItemRequest(BaseModel):
    init_data: str
    inv_id: int


class BuyRequest(BaseModel):
    init_data: str
    item_id: str


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


def load_inventory(telegram_id: int):
    result = (
        supabase.table("inventory")
        .select("id,equipped,qty,items(id,name,type,slot,rarity,sell_price)")
        .eq("telegram_id", telegram_id)
        .order("id")
        .execute()
    )
    return result.data


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


def give_starter_items(telegram_id: int):
    claim = (
        supabase.table("players")
        .update({"starter_given": True})
        .eq("telegram_id", telegram_id)
        .eq("starter_given", False)
        .execute()
    )
    if not claim.data:
        return

    rows = [
        {"telegram_id": telegram_id, "item_id": item_id}
        for item_id in STARTER_ITEMS
    ]
    supabase.table("inventory").insert(rows).execute()


def get_own_row(telegram_id: int, inv_id: int):
    result = (
        supabase.table("inventory")
        .select("id,equipped,items(slot)")
        .eq("id", inv_id)
        .eq("telegram_id", telegram_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(404, "Item not found")
    return result.data[0]


@app.get("/")
def home():
    return FileResponse(
        "static/index.html",
        headers={"Cache-Control": "no-store"}
    )


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
        give_starter_items(user["id"])
        player = load_player(user["id"])
        inventory = load_inventory(user["id"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Database error")

    return {"status": "success", "player": player, "inventory": inventory}


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


@app.post("/inventory/equip")
def equip(request: ItemRequest):
    user = verify_telegram_data(request.init_data)

    try:
        row = get_own_row(user["id"], request.inv_id)
        slot = (row.get("items") or {}).get("slot")

        if not slot:
            raise HTTPException(400, "Этот предмет нельзя надеть")

        same_slot = (
            supabase.table("inventory")
            .select("id,items!inner(slot)")
            .eq("telegram_id", user["id"])
            .eq("equipped", True)
            .eq("items.slot", slot)
            .execute()
        )
        for old in same_slot.data:
            supabase.table("inventory").update(
                {"equipped": False}
            ).eq("id", old["id"]).execute()

        supabase.table("inventory").update(
            {"equipped": True}
        ).eq("id", request.inv_id).eq("telegram_id", user["id"]).execute()

        inventory = load_inventory(user["id"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Database error")

    return {"status": "success", "inventory": inventory}


@app.post("/inventory/unequip")
def unequip(request: ItemRequest):
    user = verify_telegram_data(request.init_data)

    try:
        get_own_row(user["id"], request.inv_id)
        supabase.table("inventory").update(
            {"equipped": False}
        ).eq("id", request.inv_id).eq("telegram_id", user["id"]).execute()
        inventory = load_inventory(user["id"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Database error")

    return {"status": "success", "inventory": inventory}


@app.get("/shop/items")
def shop_items():
    try:
        result = (
            supabase.table("items")
            .select("id,name,type,slot,rarity,price,shop_category")
            .in_("shop_category", SHOP_CATEGORIES)
            .order("price")
            .execute()
        )
    except Exception:
        raise HTTPException(500, "Database error")

    return {"items": result.data}


@app.post("/shop/buy")
def shop_buy(request: BuyRequest):
    user = verify_telegram_data(request.init_data)
    tid = user["id"]

    try:
        found = (
            supabase.table("items")
            .select("id,name,price")
            .eq("id", request.item_id)
            .in_("shop_category", SHOP_CATEGORIES)
            .limit(1)
            .execute()
        )
        if not found.data:
            raise HTTPException(404, "Этого предмета нет в магазине")

        item = found.data[0]

        owned = (
            supabase.table("inventory")
            .select("id")
            .eq("telegram_id", tid)
            .execute()
        )
        if len(owned.data) >= INVENTORY_SIZE:
            raise HTTPException(400, "Инвентарь полон")

        change_balance(tid, -item["price"])

        try:
            supabase.table("inventory").insert(
                {"telegram_id": tid, "item_id": item["id"]}
            ).execute()
        except Exception:
            change_balance(tid, item["price"])
            raise HTTPException(500, "Database error")

        player = load_player(tid)
        inventory = load_inventory(tid)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Database error")

    return {
        "status": "success",
        "message": "Куплено: " + item["name"],
        "player": player,
        "inventory": inventory,
    }


@app.post("/shop/sell")
def shop_sell(request: ItemRequest):
    user = verify_telegram_data(request.init_data)
    tid = user["id"]

    try:
        found = (
            supabase.table("inventory")
            .select("id,equipped,qty,items(name,type,sell_price)")
            .eq("id", request.inv_id)
            .eq("telegram_id", tid)
            .limit(1)
            .execute()
        )
        if not found.data:
            raise HTTPException(404, "Предмет не найден")

        row = found.data[0]
        item = row["items"]

        if item["type"] != "resource" or row["equipped"]:
            raise HTTPException(400, "NPC покупает только ресурсы")

        total = item["sell_price"] * row["qty"]

        deleted = (
            supabase.table("inventory")
            .delete()
            .eq("id", request.inv_id)
            .eq("telegram_id", tid)
            .execute()
        )
        if not deleted.data:
            raise HTTPException(404, "Предмет уже продан")

        change_balance(tid, total)

        player = load_player(tid)
        inventory = load_inventory(tid)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Database error")

    return {
        "status": "success",
        "message": "Продано: " + item["name"] + " x" + str(row["qty"])
                   + " (+" + str(total) + ")",
        "player": player,
        "inventory": inventory,
    }


# Лес и озеро живут в отдельном файле rtp.py
from rtp import router as rtp_router  # noqa: E402

app.include_router(rtp_router)
# --- Прокачка (новое) ---
from progress import router as progress_router, build_player  # noqa: E402

app.include_router(progress_router)


def load_player(telegram_id: int):  # noqa: F811
    """Новая версия: уровни, статы и максимум HP."""
    return build_player(telegram_id)
# --- Бой на поляне (новое) ---
from combat import router as combat_router  # noqa: E402

app.include_router(combat_router)
