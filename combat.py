import random
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import (
    InitRequest,
    change_balance,
    clear_session,
    commit_session,
    load_session,
    safe,
    start_session,
    supabase,
    user_id,
)
from inventory import load_inventory
from progress import award_xp, build_player

router = APIRouter()

PLAYER_COOLDOWN = 1.0
COOLDOWN_SLACK = 0.15
DEFAULT_INTERVAL = 3.5
ARMOR_K = 40
REGEN_INTERVAL = 5.0
PLAYER_BASE_MISS = 5
MAX_MISS = 75
HEAL_COOLDOWN = 6.0
FLEE_CHANCE = 0.7
FLEE_RETRY = 3.0
DEATH_LOSS = 0.5
MEDIUM_CHANCE = 0.20
COUNT_WEIGHTS = [45, 35, 20]


class AttackRequest(BaseModel):
    init_data: str
    mob_id: int


class HealRequest(BaseModel):
    init_data: str
    inv_id: int


# ---------- создание боя ----------

def load_mobs(tier):
    r = supabase.table("mobs").select("*").eq("tier", tier).execute()
    if not r.data:
        raise HTTPException(500, "Нет мобов в таблице mobs")
    return r.data


def make_group():
    n = random.choices([1, 2, 3], weights=COUNT_WEIGHTS)[0]
    medium = 0
    if random.random() < MEDIUM_CHANCE:
        medium = random.randint(1, min(2, n))

    picks = [random.choice(load_mobs("medium")) for _ in range(medium)]
    picks += [random.choice(load_mobs("easy")) for _ in range(n - medium)]
    random.shuffle(picks)
    return picks


def start_clearing(tid):
    totals = build_player(tid)["totals"]
    now = time.time()

    mobs = []
    for i, m in enumerate(make_group()):
        interval = float(m.get("attack_interval") or DEFAULT_INTERVAL)
        mobs.append({
            "id": i,
            "name": m["name"],
            "emoji": m["emoji"],
            "hp": float(m["hp"]),
            "max_hp": m["hp"],
            "dmg": m["damage"],
            "xp": m["xp"],
            "silver": m["silver"],
            "interval": interval,
            "miss": m["miss"],
            "evasion": m["evasion"],
            "n": 0,
            "next": now + interval + i * 0.7,
        })

    data = {
        "mobs": mobs,
        "php": float(totals["max_hp"]),
        "pmax": totals["max_hp"],
        "damage": totals["damage"],
        "crit": totals["crit"],
        "armor": totals["armor"],
        "regen": totals["regen"],
        "evasion": totals["evasion"],
        "seed": str(random.random()),
        "last_tick": now,
        "last_attack": 0,
        "heal_at": 0,
        "flee_at": 0,
        "done": False,
    }
    start_session(tid, "clearing", data)
    return fight_view(data, now, [])


# ---------- ход времени ----------

def regen_tick(data, seconds):
    if seconds > 0:
        data["php"] = min(
            data["pmax"],
            data["php"] + data["regen"] * seconds / REGEN_INTERVAL,
        )


def advance(data, now):
    """Применяет всё, что случилось с last_tick до now.
    Исход ударов мобов зависит только от seed и номера удара,
    поэтому повторный пересчёт даёт тот же результат.
    Возвращает список событий."""
    out = []
    if data["php"] <= 0:
        return out

    reduction = data["armor"] / (data["armor"] + ARMOR_K)

    raw = []
    for m in data["mobs"]:
        if m["hp"] <= 0:
            continue
        t = m["next"]
        idx = 0
        while t <= now and idx < 100:
            raw.append((t, m, m["n"] + idx))
            t += m["interval"]
            idx += 1
        m["next"] = t
        m["n"] += idx
    raw.sort(key=lambda e: e[0])

    cursor = data["last_tick"]
    for t, m, k in raw:
        regen_tick(data, t - cursor)
        cursor = t

        eid = str(m["id"]) + ":" + str(k)
        rng = random.Random(data["seed"] + ":" + eid)
        miss = min(MAX_MISS, m["miss"] + data["evasion"])

        if rng.random() * 100 < miss:
            out.append({"id": eid, "mob": m["name"], "hit": False, "dmg": 0})
            continue

        dmg = round(max(1.0, m["dmg"] * (1 - reduction)), 1)
        data["php"] -= dmg
        out.append({"id": eid, "mob": m["name"], "hit": True, "dmg": dmg})
        if data["php"] <= 0:
            data["php"] = 0
            return out

    regen_tick(data, now - cursor)
    data["last_tick"] = now
    return out


def fight_view(data, now, events):
    return {
        "place": "clearing",
        "php": round(data["php"], 1),
        "pmax": data["pmax"],
        "done": data["done"],
        "ready_in": round(max(0.0, PLAYER_COOLDOWN - (now - data["last_attack"])), 2),
        "heal_in": round(max(0.0, data["heal_at"] - now), 1),
        "events": events,
        "mobs": [
            {
                "id": m["id"],
                "name": m["name"],
                "emoji": m["emoji"],
                "hp": round(m["hp"], 1),
                "max_hp": m["max_hp"],
            }
            for m in data["mobs"]
        ],
    }


def process_death(tid, ver):
    # commit_session пропустит только один запрос, двойной штраф невозможен
    commit_session(tid, {"dead": True}, ver)

    r = (
        supabase.table("players")
        .select("balance")
        .eq("telegram_id", tid)
        .limit(1)
        .execute()
    )
    balance = r.data[0]["balance"] if r.data else 0
    lost = int(balance * DEATH_LOSS)
    if lost > 0:
        change_balance(tid, -lost)

    clear_session(tid)
    return {
        "dead": True,
        "lost": lost,
        "message": "Ты погиб. Потеряно серебра: " + str(lost),
    }


def clearing_state(tid, data, ver):
    """Состояние боя при возвращении в игру."""
    if data.get("dead"):
        clear_session(tid)
        return {"place": None}

    now = time.time()
    events = advance(data, now)
    if data["php"] <= 0:
        return process_death(tid, ver)
    return fight_view(data, now, events)


def load_fight(tid):
    data, ver = load_session(tid, "clearing")
    if data.get("dead"):
        raise HTTPException(400, "Ты сейчас не здесь")
    return data, ver


# ---------- маршруты ----------

@router.post("/fight/state")
@safe
def fight_state(req: InitRequest):
    tid = user_id(req.init_data)
    data, ver = load_fight(tid)

    now = time.time()
    events = advance(data, now)
    if data["php"] <= 0:
        return process_death(tid, ver)
    return fight_view(data, now, events)


@router.post("/fight/attack")
@safe
def fight_attack(req: AttackRequest):
    tid = user_id(req.init_data)
    data, ver = load_fight(tid)

    now = time.time()
    events = advance(data, now)
    if data["php"] <= 0:
        return process_death(tid, ver)

    if now - data["last_attack"] < PLAYER_COOLDOWN - COOLDOWN_SLACK:
        raise HTTPException(400, "Оружие ещё не готово")

    mob = next(
        (m for m in data["mobs"] if m["id"] == req.mob_id and m["hp"] > 0),
        None,
    )
    if mob is None:
        raise HTTPException(404, "Этот моб уже побеждён")

    data["last_attack"] = now
    killed = None

    miss = min(MAX_MISS, PLAYER_BASE_MISS + mob["evasion"])
    if random.random() * 100 < miss:
        hit = {"miss": True}
    else:
        crit = random.random() * 100 < data["crit"]
        dmg = round(data["damage"] * (1.5 if crit else 1.0), 1)
        mob["hp"] = round(max(0.0, mob["hp"] - dmg), 1)
        hit = {"miss": False, "damage": dmg, "crit": crit}

        if mob["hp"] <= 0:
            killed = {
                "name": mob["name"],
                "xp": mob["xp"],
                "silver": mob["silver"],
            }
            if all(m["hp"] <= 0 for m in data["mobs"]):
                data["done"] = True

    commit_session(tid, data, ver)

    view = fight_view(data, now, events)
    view["hit"] = hit
    view["killed"] = killed

    if killed:
        change_balance(tid, killed["silver"])
        award_xp(tid, killed["xp"])
        view["player"] = build_player(tid)
    return view


@router.post("/fight/heal")
@safe
def fight_heal(req: HealRequest):
    tid = user_id(req.init_data)
    data, ver = load_fight(tid)

    now = time.time()
    events = advance(data, now)
    if data["php"] <= 0:
        return process_death(tid, ver)

    if data["done"]:
        raise HTTPException(400, "Бой уже окончен")
    if now < data["heal_at"]:
        raise HTTPException(400, "Лечение ещё не готово")
    if data["php"] >= data["pmax"]:
        raise HTTPException(400, "HP уже полное")

    r = (
        supabase.table("inventory")
        .select("id,item_id,qty,items(name,type,heal)")
        .eq("id", req.inv_id)
        .eq("telegram_id", tid)
        .limit(1)
        .execute()
        .data
    )
    if not r:
        raise HTTPException(404, "Предмет не найден")
    row = r[0]
    item = row["items"] or {}
    amount = item.get("heal") or 0
    if item.get("type") != "heal" or amount <= 0:
        raise HTTPException(400, "Этим нельзя лечиться")

    # сначала тратим предмет, потом сохраняем бой
    if row["qty"] > 1:
        spent = (
            supabase.table("inventory")
            .update({"qty": row["qty"] - 1})
            .eq("id", row["id"])
            .eq("qty", row["qty"])
            .execute()
        )
    else:
        spent = (
            supabase.table("inventory")
            .delete()
            .eq("id", row["id"])
            .eq("telegram_id", tid)
            .execute()
        )
    if not spent.data:
        raise HTTPException(409, "Попробуй ещё раз")

    data["php"] = min(data["pmax"], data["php"] + amount)
    data["heal_at"] = now + HEAL_COOLDOWN

    try:
        commit_session(tid, data, ver)
    except HTTPException:
        # бой не сохранился: вернуть предмет
        if row["qty"] > 1:
            supabase.table("inventory").update(
                {"qty": row["qty"]}
            ).eq("id", row["id"]).execute()
        else:
            supabase.table("inventory").insert(
                {"telegram_id": tid, "item_id": row["item_id"], "qty": 1}
            ).execute()
        raise

    view = fight_view(data, now, events)
    view["healed"] = {"name": item["name"], "amount": amount}
    view["inventory"] = load_inventory(tid)
    return view


@router.post("/fight/flee")
@safe
def fight_flee(req: InitRequest):
    tid = user_id(req.init_data)
    data, ver = load_fight(tid)

    now = time.time()
    events = advance(data, now)
    if data["php"] <= 0:
        return process_death(tid, ver)

    if data["done"]:
        clear_session(tid)
        return {"fled": True, "message": "Ты вернулся на спавн"}

    if now < data["flee_at"]:
        raise HTTPException(400, "Подожди перед новой попыткой")

    if random.random() < FLEE_CHANCE:
        clear_session(tid)
        return {"fled": True, "message": "Ты сбежал"}

    data["flee_at"] = now + FLEE_RETRY
    commit_session(tid, data, ver)
    view = fight_view(data, now, events)
    view["fled"] = False
    view["message"] = "Не удалось сбежать!"
    return view
