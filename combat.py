import random
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from main import supabase, verify_telegram_data, change_balance
from progress import award_xp, build_player
from rtp import (
    safe,
    start_session,
    load_session,
    commit_session,
    make_trees,
    make_treasure,
    forest_payload,
    rtp_current,
)

router = APIRouter()

PLACE_WEIGHTS = {"forest": 40, "lake": 18, "clearing": 30}

PLAYER_COOLDOWN = 1.0
COOLDOWN_SLACK = 0.15
MOB_INTERVAL = 2.0
ARMOR_K = 40
REGEN_INTERVAL = 5.0
FLEE_CHANCE = 0.7
FLEE_RETRY = 3.0
DEATH_LOSS = 0.5
MEDIUM_CHANCE = 0.20
COUNT_WEIGHTS = [45, 35, 20]


class InitRequest(BaseModel):
    init_data: str


class AttackRequest(BaseModel):
    init_data: str
    mob_id: int


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
        mobs.append({
            "id": i,
            "name": m["name"],
            "emoji": m["emoji"],
            "hp": float(m["hp"]),
            "max_hp": m["hp"],
            "dmg": m["damage"],
            "xp": m["xp"],
            "silver": m["silver"],
            "next": now + MOB_INTERVAL + i * 0.7,
        })

    data = {
        "mobs": mobs,
        "php": float(totals["max_hp"]),
        "pmax": totals["max_hp"],
        "damage": totals["damage"],
        "crit": totals["crit"],
        "armor": totals["armor"],
        "regen": totals["regen"],
        "last_tick": now,
        "last_attack": 0,
        "flee_at": 0,
        "done": False,
    }
    start_session(tid, "clearing", data)
    return fight_view(data, now)


# ---------- ход времени ----------

def heal(data, seconds):
    if seconds > 0:
        data["php"] = min(
            data["pmax"],
            data["php"] + data["regen"] * seconds / REGEN_INTERVAL,
        )


def advance(data, now):
    """Применяет всё, что случилось с last_tick до now: атаки мобов и лечение."""
    if data["php"] <= 0:
        return

    reduction = data["armor"] / (data["armor"] + ARMOR_K)

    events = []
    for m in data["mobs"]:
        if m["hp"] <= 0:
            continue
        t = m["next"]
        guard = 0
        while t <= now and guard < 100:
            events.append((t, m))
            t += MOB_INTERVAL
            guard += 1
        m["next"] = t
    events.sort(key=lambda e: e[0])

    cursor = data["last_tick"]
    for t, m in events:
        heal(data, t - cursor)
        cursor = t
        data["php"] -= max(1.0, m["dmg"] * (1 - reduction))
        if data["php"] <= 0:
            data["php"] = 0
            return

    heal(data, now - cursor)
    data["last_tick"] = now


def fight_view(data, now):
    ready = max(0.0, PLAYER_COOLDOWN - (now - data["last_attack"]))
    return {
        "place": "clearing",
        "php": round(data["php"], 1),
        "pmax": data["pmax"],
        "done": data["done"],
        "ready_in": round(ready, 2),
        "mobs": [
            {
                "id": m["id"],
                "name": m["name"],
                "emoji": m["emoji"],
                "hp": round(m["hp"], 1),
                "max_hp": m["max_hp"],
                "next_in": round(max(0.0, m["next"] - now), 1),
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

    supabase.table("sessions").delete().eq("telegram_id", tid).execute()
    return {
        "dead": True,
        "lost": lost,
        "message": "Ты погиб. Потеряно серебра: " + str(lost),
    }


# ---------- маршруты ----------

@router.post("/rtp/roll")
@safe
def rtp_roll(req: InitRequest):
    tid = verify_telegram_data(req.init_data)["id"]

    cur = (
        supabase.table("sessions")
        .select("kind,data")
        .eq("telegram_id", tid)
        .limit(1)
        .execute()
        .data
    )
    if cur and cur[0]["kind"] == "clearing":
        d = cur[0]["data"]
        if not d.get("done") and not d.get("dead"):
            raise HTTPException(400, "Ты в бою! Сначала победи или сбеги")

    place = random.choices(
        list(PLACE_WEIGHTS), weights=list(PLACE_WEIGHTS.values())
    )[0]

    if place == "clearing":
        return start_clearing(tid)

    if place == "forest":
        data = {"trees": make_trees(), "treasure": make_treasure()}
        start_session(tid, "forest", data)
        return forest_payload(data)

    start_session(tid, "lake", {"phase": "idle"})
    return {"place": "lake", "phase": "idle", "wait_left": 0}


@router.post("/rtp/current2")
@safe
def rtp_current2(req: InitRequest):
    tid = verify_telegram_data(req.init_data)["id"]
    r = (
        supabase.table("sessions")
        .select("kind,data,ver")
        .eq("telegram_id", tid)
        .limit(1)
        .execute()
    )
    if not r.data:
        return {"place": None}

    s = r.data[0]
    if s["kind"] != "clearing":
        return rtp_current(req)

    data, ver = s["data"], s["ver"]
    if data.get("dead"):
        supabase.table("sessions").delete().eq("telegram_id", tid).execute()
        return {"place": None}

    now = time.time()
    advance(data, now)
    if data["php"] <= 0:
        return process_death(tid, ver)
    return fight_view(data, now)


@router.post("/fight/state")
@safe
def fight_state(req: InitRequest):
    tid = verify_telegram_data(req.init_data)["id"]
    data, ver = load_session(tid, "clearing")
    if data.get("dead"):
        raise HTTPException(400, "Ты сейчас не здесь")

    now = time.time()
    advance(data, now)
    if data["php"] <= 0:
        return process_death(tid, ver)
    return fight_view(data, now)


@router.post("/fight/attack")
@safe
def fight_attack(req: AttackRequest):
    tid = verify_telegram_data(req.init_data)["id"]
    data, ver = load_session(tid, "clearing")
    if data.get("dead"):
        raise HTTPException(400, "Ты сейчас не здесь")

    now = time.time()
    advance(data, now)
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

    crit = random.random() * 100 < data["crit"]
    dmg = round(data["damage"] * (1.5 if crit else 1.0), 1)
    mob["hp"] = round(max(0.0, mob["hp"] - dmg), 1)
    data["last_attack"] = now

    killed = None
    if mob["hp"] <= 0:
        killed = {
            "name": mob["name"],
            "xp": mob["xp"],
            "silver": mob["silver"],
        }
        if all(m["hp"] <= 0 for m in data["mobs"]):
            data["done"] = True

    commit_session(tid, data, ver)

    if killed:
        change_balance(tid, killed["silver"])
        award_xp(tid, killed["xp"])

    view = fight_view(data, now)
    view["hit"] = {"damage": dmg, "crit": crit}
    view["killed"] = killed
    return view


@router.post("/fight/flee")
@safe
def fight_flee(req: InitRequest):
    tid = verify_telegram_data(req.init_data)["id"]
    data, ver = load_session(tid, "clearing")
    if data.get("dead"):
        raise HTTPException(400, "Ты сейчас не здесь")

    now = time.time()
    advance(data, now)
    if data["php"] <= 0:
        return process_death(tid, ver)

    if data["done"]:
        supabase.table("sessions").delete().eq("telegram_id", tid).execute()
        return {"fled": True, "message": "Ты вернулся на спавн"}

    if now < data["flee_at"]:
        raise HTTPException(400, "Подожди перед новой попыткой")

    if random.random() < FLEE_CHANCE:
        supabase.table("sessions").delete().eq("telegram_id", tid).execute()
        return {"fled": True, "message": "Ты сбежал"}

    data["flee_at"] = now + FLEE_RETRY
    commit_session(tid, data, ver)
    view = fight_view(data, now)
    view["fled"] = False
    view["message"] = "Не удалось сбежать!"
    return view


@router.get("/fight.js")
def fight_js():
    return FileResponse(
        "static/fight.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )
