import functools
import random
import time
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from main import (
    supabase,
    verify_telegram_data,
    load_inventory,
    INVENTORY_SIZE,
)

router = APIRouter()

AXES = ["wooden_axe", "stone_axe", "iron_axe"]
SHOVELS = ["shovel"]
RODS = ["fishing_rod"]

PLACE_WEIGHTS = {"forest": 40, "lake": 18}

FOREST_W = 720
FOREST_H = 1040
TREE_COUNT = 16
CHOP_GAP = 10
CHOP_HITS = 6
GAP_TOLERANCE = 1.0
TREASURE_CHANCE = 0.20
GOLD_CHANCE = 0.20

DIRS = ["left", "right", "up", "down"]
FISH = [
    ("fish", "Обычная рыба", 65, 6),
    ("fish_good", "Хорошая рыба", 25, 8),
    ("fish_rare", "Редкая рыба", 10, 10),
]
WAIT_MIN = 20
WAIT_MAX = 60
SHOW_SECONDS = 10
ANSWER_SECONDS = 30
NET_SLACK = 3

NAMES = {
    "wood": "Бревно",
    "iron_ore": "Руда",
    "fish": "Обычная рыба",
    "fish_good": "Хорошая рыба",
    "fish_rare": "Редкая рыба",
    "gold_ingot": "Золотой слиток",
}


class InitRequest(BaseModel):
    init_data: str


class TreeRequest(BaseModel):
    init_data: str
    tree_id: int


class AnswerRequest(BaseModel):
    init_data: str
    answer: List[str]


def safe(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except HTTPException:
            raise
        except Exception as e:
            print("RTP ERROR:", repr(e))
            raise HTTPException(500, "Database error")
    return wrapper


# ---------- сессии (где сейчас игрок) ----------

def start_session(tid, kind, data):
    supabase.table("sessions").upsert(
        {"telegram_id": tid, "kind": kind, "data": data, "ver": 0},
        on_conflict="telegram_id",
    ).execute()


def load_session(tid, kind):
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


def commit_session(tid, data, ver):
    """Сохраняет, только если никто не изменил сессию раньше (защита от двойных нажатий)."""
    ok = (
        supabase.table("sessions")
        .update({"data": data, "ver": ver + 1})
        .eq("telegram_id", tid)
        .eq("ver", ver)
        .execute()
    )
    if not ok.data:
        raise HTTPException(409, "Слишком быстро, попробуй ещё раз")


# ---------- предметы ----------

def has_item(tid, item_ids):
    r = (
        supabase.table("inventory")
        .select("id")
        .eq("telegram_id", tid)
        .in_("item_id", list(item_ids))
        .limit(1)
        .execute()
    )
    return bool(r.data)


def check_space(tid, loot):
    rows = (
        supabase.table("inventory")
        .select("item_id")
        .eq("telegram_id", tid)
        .execute()
        .data
    )
    have = {r["item_id"] for r in rows}
    new_slots = len([i for i in loot if i not in have])
    if len(rows) + new_slots > INVENTORY_SIZE:
        raise HTTPException(
            400, "Инвентарь полон. Продай что-нибудь торговцу"
        )


def add_items(tid, loot):
    """Добавляет ресурсы; одинаковые складываются в одну стопку."""
    check_space(tid, loot)
    rows = (
        supabase.table("inventory")
        .select("id,item_id,qty")
        .eq("telegram_id", tid)
        .execute()
        .data
    )
    have = {}
    for r in rows:
        have.setdefault(r["item_id"], r)

    for item_id, qty in loot.items():
        row = have.get(item_id)
        if row:
            ok = (
                supabase.table("inventory")
                .update({"qty": row["qty"] + qty})
                .eq("id", row["id"])
                .eq("qty", row["qty"])
                .execute()
            )
            if not ok.data:
                raise HTTPException(409, "Попробуй ещё раз")
        else:
            supabase.table("inventory").insert(
                {"telegram_id": tid, "item_id": item_id, "qty": qty}
            ).execute()


def loot_text(loot):
    return ", ".join(
        NAMES.get(i, i) + " x" + str(q) for i, q in loot.items()
    )


# ---------- лес ----------

def make_trees():
    trees = []
    tries = 0
    while len(trees) < TREE_COUNT and tries < 1000:
        tries += 1
        x = random.randint(40, FOREST_W - 40)
        y = random.randint(60, FOREST_H - 130)
        if all((x - t["x"]) ** 2 + (y - t["y"]) ** 2 > 90 ** 2 for t in trees):
            trees.append({
                "id": len(trees), "x": x, "y": y,
                "hits": 0, "last": 0, "felled": False,
            })
    return trees


def make_treasure():
    if random.random() >= TREASURE_CHANCE:
        return None
    return {
        "x": random.randint(40, FOREST_W - 40),
        "y": random.randint(60, FOREST_H - 130),
        "dug": False,
    }


def tree_view(tree, now):
    started = tree["last"] > 0
    wait = 0.0
    if started and not tree["felled"]:
        wait = max(0.0, CHOP_GAP - (now - tree["last"]))
    return {
        "id": tree["id"], "x": tree["x"], "y": tree["y"],
        "hits": tree["hits"], "felled": tree["felled"],
        "started": started, "wait": round(wait, 1),
    }


def forest_payload(data):
    now = time.time()
    t = data.get("treasure")
    return {
        "place": "forest",
        "width": FOREST_W,
        "height": FOREST_H,
        "start": {"x": FOREST_W // 2, "y": FOREST_H - 40},
        "hits_needed": CHOP_HITS,
        "trees": [tree_view(x, now) for x in data["trees"]],
        "treasure": (
            {"x": t["x"], "y": t["y"], "dug": t["dug"]} if t else None
        ),
    }


def roll_treasure():
    loot = {}
    for item_id in random.sample(
        ["iron_ore", "wood", "fish"], random.randint(1, 3)
    ):
        loot[item_id] = random.randint(1, 3)
    if random.random() < GOLD_CHANCE:
        loot["gold_ingot"] = 1
    return loot


@router.post("/rtp/go")
@safe
def rtp_go(req: InitRequest):
    tid = verify_telegram_data(req.init_data)["id"]

    place = random.choices(
        list(PLACE_WEIGHTS), weights=list(PLACE_WEIGHTS.values())
    )[0]

    if place == "forest":
        data = {"trees": make_trees(), "treasure": make_treasure()}
        start_session(tid, "forest", data)
        return forest_payload(data)

    start_session(tid, "lake", {"phase": "idle"})
    return {"place": "lake", "phase": "idle", "wait_left": 0}


@router.post("/rtp/current")
@safe
def rtp_current(req: InitRequest):
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
    if s["kind"] == "forest":
        return forest_payload(s["data"])

    d = s["data"]
    if d.get("phase") == "bite":
        # перезашёл посреди мини-игры: рыба сорвалась
        d = {"phase": "idle"}
        commit_session(tid, d, s["ver"])

    wait_left = 0
    if d.get("phase") == "waiting":
        wait_left = max(0, int(d["bite_at"] - time.time() + 0.5))
    return {
        "place": "lake",
        "phase": d.get("phase", "idle"),
        "wait_left": wait_left,
    }


@router.post("/rtp/leave")
@safe
def rtp_leave(req: InitRequest):
    tid = verify_telegram_data(req.init_data)["id"]
    supabase.table("sessions").delete().eq("telegram_id", tid).execute()
    return {"status": "success"}


@router.post("/forest/chop")
@safe
def forest_chop(req: TreeRequest):
    tid = verify_telegram_data(req.init_data)["id"]
    data, ver = load_session(tid, "forest")

    if not has_item(tid, AXES):
        raise HTTPException(400, "Нужен топор. Купи его у торговца")

    tree = next(
        (t for t in data["trees"] if t["id"] == req.tree_id), None
    )
    if tree is None or tree["felled"]:
        raise HTTPException(404, "Это дерево уже срублено")

    now = time.time()
    loot = None

    if tree["last"] == 0:
        tree["last"] = now
        message = "Рубка началась. Нажимай «Рубить» каждые 10 секунд"
    else:
        left = CHOP_GAP - (now - tree["last"])
        if left > GAP_TOLERANCE:
            raise HTTPException(
                400, "Рано. Подожди ещё " + str(int(left + 0.5)) + " сек"
            )
        tree["hits"] += 1
        tree["last"] = now
        message = "Удар " + str(tree["hits"]) + " из " + str(CHOP_HITS)

        if tree["hits"] >= CHOP_HITS:
            loot = {"wood": random.randint(3, 6)}
            check_space(tid, loot)
            tree["felled"] = True
            message = "Дерево срублено! " + loot_text(loot)

    commit_session(tid, data, ver)
    if loot:
        add_items(tid, loot)

    return {
        "tree": tree_view(tree, now),
        "message": message,
        "inventory": load_inventory(tid),
    }


@router.post("/forest/dig")
@safe
def forest_dig(req: InitRequest):
    tid = verify_telegram_data(req.init_data)["id"]
    data, ver = load_session(tid, "forest")

    if not has_item(tid, SHOVELS):
        raise HTTPException(400, "Нужна лопата. Купи её у торговца")

    t = data.get("treasure")
    if not t or t["dug"]:
        raise HTTPException(404, "Здесь нечего копать")

    loot = roll_treasure()
    check_space(tid, loot)
    t["dug"] = True
    commit_session(tid, data, ver)
    add_items(tid, loot)

    return {
        "message": "Клад! " + loot_text(loot),
        "treasure": {"x": t["x"], "y": t["y"], "dug": True},
        "inventory": load_inventory(tid),
    }


# ---------- озеро ----------

@router.post("/fish/start")
@safe
def fish_start(req: InitRequest):
    tid = verify_telegram_data(req.init_data)["id"]
    data, ver = load_session(tid, "lake")

    if not has_item(tid, RODS):
        raise HTTPException(400, "Нужна удочка. Купи её у торговца")

    now = time.time()
    phase = data.get("phase", "idle")
    busy = phase == "waiting" or (
        phase == "bite" and now <= data.get("deadline", 0)
    )
    if busy:
        raise HTTPException(400, "Ты уже ловишь рыбу")

    entry = random.choices(FISH, weights=[f[2] for f in FISH])[0]
    seq = [random.choice(DIRS) for _ in range(entry[3])]
    wait = random.randint(WAIT_MIN, WAIT_MAX)

    new = {
        "phase": "waiting",
        "bite_at": now + wait,
        "fish": entry[0],
        "seq": seq,
    }
    commit_session(tid, new, ver)
    return {"wait": wait}


@router.post("/fish/bite")
@safe
def fish_bite(req: InitRequest):
    tid = verify_telegram_data(req.init_data)["id"]
    data, ver = load_session(tid, "lake")

    if data.get("phase") != "waiting":
        raise HTTPException(400, "Сначала забрось удочку")

    now = time.time()
    if now < data["bite_at"] - 1.5:
        raise HTTPException(400, "Пока не клюёт")

    data["phase"] = "bite"
    data["deadline"] = now + SHOW_SECONDS + ANSWER_SECONDS + NET_SLACK
    commit_session(tid, data, ver)

    return {
        "sequence": data["seq"],
        "show_seconds": SHOW_SECONDS,
        "answer_seconds": ANSWER_SECONDS,
    }


@router.post("/fish/finish")
@safe
def fish_finish(req: AnswerRequest):
    tid = verify_telegram_data(req.init_data)["id"]
    data, ver = load_session(tid, "lake")

    if data.get("phase") != "bite":
        raise HTTPException(400, "Рыба не клюёт")

    now = time.time()
    success = False

    if now > data["deadline"]:
        message = "Время вышло, рыба сорвалась"
    elif req.answer != data["seq"]:
        message = "Неверно, рыба сорвалась"
    else:
        success = True
        message = "Поймана рыба: " + NAMES.get(data["fish"], data["fish"])

    fish_id = data["fish"]
    commit_session(tid, {"phase": "idle"}, ver)

    if success:
        try:
            add_items(tid, {fish_id: 1})
        except HTTPException:
            success = False
            message = "Инвентарь полон, рыба уплыла"

    return {
        "success": success,
        "message": message,
        "inventory": load_inventory(tid),
                }
from fastapi.responses import FileResponse  # noqa: E402


class DeleteRequest(BaseModel):
    init_data: str
    inv_id: int


@router.post("/inventory/delete")
@safe
def inventory_delete(req: DeleteRequest):
    tid = verify_telegram_data(req.init_data)["id"]
    r = (
        supabase.table("inventory")
        .select("id,equipped")
        .eq("id", req.inv_id)
        .eq("telegram_id", tid)
        .limit(1)
        .execute()
    )
    if not r.data:
        raise HTTPException(404, "Предмет не найден")
    if r.data[0]["equipped"]:
        raise HTTPException(400, "Сначала сними предмет")

    supabase.table("inventory").delete().eq(
        "id", req.inv_id
    ).eq("telegram_id", tid).execute()
    return {"message": "Предмет удалён", "inventory": load_inventory(tid)}


@router.get("/js/{name}")
def js_file(name: str):
    if name not in ("ui.js", "world.js"):
        raise HTTPException(404, "Not found")
    return FileResponse(
        "static/" + name,
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )
