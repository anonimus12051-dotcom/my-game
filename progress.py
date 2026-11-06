from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from main import supabase, verify_telegram_data

router = APIRouter()

MAX_LEVEL = 50
POINTS_PER_LEVEL = 3
BASE_HP = 100
BASE_DAMAGE = 1

STAT_COLS = {
    "damage": "stat_damage",
    "crit": "stat_crit",
    "hp": "stat_hp",
    "armor": "stat_armor",
    "regen": "stat_regen",
}
PER_POINT = {
    "damage": 0.5,
    "crit": 0.3,
    "hp": 3,
    "armor": 0.5,
    "regen": 0.5,
}

FIELDS = (
    "telegram_id,username,first_name,photo_url,balance,level,xp,hp,"
    "class,stat_points,stat_damage,stat_crit,stat_hp,stat_armor,stat_regen"
)


class InitRequest(BaseModel):
    init_data: str


class SpendRequest(BaseModel):
    init_data: str
    stat: str
    amount: int = 1


def xp_needed(level: int) -> int:
    """Опыт для перехода с уровня level на следующий: 100, 110, 121..."""
    return round(100 * 1.1 ** (level - 1))


def equipped_bonus(tid: int):
    """Сумма урона, брони и HP от надетых предметов."""
    rows = (
        supabase.table("inventory")
        .select("items(damage,armor,hp_bonus)")
        .eq("telegram_id", tid)
        .eq("equipped", True)
        .execute()
        .data
    )
    damage = armor = hp = 0
    for r in rows:
        it = r.get("items") or {}
        damage += it.get("damage") or 0
        armor += it.get("armor") or 0
        hp += it.get("hp_bonus") or 0
    return damage, armor, hp


def build_player(tid: int):
    r = (
        supabase.table("players")
        .select(FIELDS)
        .eq("telegram_id", tid)
        .limit(1)
        .execute()
    )
    if not r.data:
        raise HTTPException(404, "Player not found")

    p = r.data[0]
    eq_damage, eq_armor, eq_hp = equipped_bonus(tid)
    max_hp = BASE_HP + int(PER_POINT["hp"] * p["stat_hp"]) + eq_hp

    p["max_level"] = MAX_LEVEL
    p["xp_to_next"] = xp_needed(p["level"]) if p["level"] < MAX_LEVEL else 0
    p["max_hp"] = max_hp
    p["stats"] = {
        key: {
            "points": p[col],
            "bonus": round(p[col] * PER_POINT[key], 1),
        }
        for key, col in STAT_COLS.items()
    }
    p["totals"] = {
        "damage": round(
            BASE_DAMAGE + eq_damage + p["stat_damage"] * PER_POINT["damage"], 1
        ),
        "crit": round(p["stat_crit"] * PER_POINT["crit"], 1),
        "max_hp": max_hp,
        "armor": round(eq_armor + p["stat_armor"] * PER_POINT["armor"], 1),
        "regen": round(p["stat_regen"] * PER_POINT["regen"], 1),
    }

    # Пока нет боя и лечения, HP всегда полный
    if p["hp"] != max_hp:
        supabase.table("players").update(
            {"hp": max_hp}
        ).eq("telegram_id", tid).execute()
        p["hp"] = max_hp

    return p


def award_xp(tid: int, amount: int):
    for _ in range(5):
        r = (
            supabase.table("players")
            .select("level,xp,stat_points")
            .eq("telegram_id", tid)
            .limit(1)
            .execute()
        )
        if not r.data:
            return
        p = r.data[0]
        level, xp, points = p["level"], p["xp"], p["stat_points"]
        if level >= MAX_LEVEL:
            return

        xp += amount
        while level < MAX_LEVEL and xp >= xp_needed(level):
            xp -= xp_needed(level)
            level += 1
            points += POINTS_PER_LEVEL
        if level >= MAX_LEVEL:
            xp = 0

        ok = (
            supabase.table("players")
            .update({"level": level, "xp": xp, "stat_points": points})
            .eq("telegram_id", tid)
            .eq("level", p["level"])
            .eq("xp", p["xp"])
            .execute()
        )
        if ok.data:
            return


def award_loot_xp(tid: int, loot: dict):
    """Опыт за добытые ресурсы (колонка xp в таблице items)."""
    try:
        rows = (
            supabase.table("items")
            .select("id,xp")
            .in_("id", list(loot))
            .execute()
            .data
        )
        total = sum(r["xp"] * loot[r["id"]] for r in rows)
        if total > 0:
            award_xp(tid, total)
    except Exception as e:
        print("XP ERROR:", repr(e))


@router.get("/items/catalog")
def items_catalog():
    try:
        r = (
            supabase.table("items")
            .select("id,name,type,slot,rarity,damage,armor,hp_bonus")
            .execute()
        )
    except Exception as e:
        print("CATALOG ERROR:", repr(e))
        raise HTTPException(500, "Database error")
    return {"items": {i["id"]: i for i in r.data}}


@router.post("/profile/get")
def profile_get(req: InitRequest):
    tid = verify_telegram_data(req.init_data)["id"]
    try:
        return {"player": build_player(tid)}
    except HTTPException:
        raise
    except Exception as e:
        print("PROFILE ERROR:", repr(e))
        raise HTTPException(500, "Database error")


@router.post("/profile/spend")
def profile_spend(req: SpendRequest):
    tid = verify_telegram_data(req.init_data)["id"]

    if req.stat not in STAT_COLS:
        raise HTTPException(400, "Неизвестная характеристика")
    if req.amount < 1 or req.amount > 100:
        raise HTTPException(400, "Неверное количество")

    col = STAT_COLS[req.stat]

    try:
        for _ in range(5):
            r = (
                supabase.table("players")
                .select("stat_points," + col)
                .eq("telegram_id", tid)
                .limit(1)
                .execute()
            )
            if not r.data:
                raise HTTPException(404, "Player not found")
            row = r.data[0]

            if row["stat_points"] < req.amount:
                raise HTTPException(400, "Не хватает очков")

            ok = (
                supabase.table("players")
                .update({
                    "stat_points": row["stat_points"] - req.amount,
                    col: row[col] + req.amount,
                })
                .eq("telegram_id", tid)
                .eq("stat_points", row["stat_points"])
                .eq(col, row[col])
                .execute()
            )
            if ok.data:
                return {"status": "success", "player": build_player(tid)}

        raise HTTPException(409, "Попробуй ещё раз")
    except HTTPException:
        raise
    except Exception as e:
        print("SPEND ERROR:", repr(e))
        raise HTTPException(500, "Database error")
