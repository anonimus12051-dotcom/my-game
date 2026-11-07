import random
import time
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from combat import clearing_state, start_clearing
from core import (
    InitRequest,
    clear_session,
    commit_session,
    load_session,
    safe,
    start_session,
    supabase,
    user_id,
)
from inventory import add_items, check_space, has_item, load_inventory
from progress import build_player

router = APIRouter()

PLACE_WEIGHTS = {"forest": 40, "lake": 18, "clearing": 30}

# секунд между ударами топором (чем лучше топор, тем быстрее)
AXE_GAP = {
    "wooden_axe": 10,
    "stone_axe": 9,
    "iron_axe": 8,
    "prima_axe": 7,
    "crystal_axe": 6,
}
DEFAULT_GAP = 10
SHOVELS = ["shovel"]
RODS = ["fishing_rod"]

FOREST_W = 720
FOREST_H = 1040
TREE_COUNT = 16
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


class TreeRequest(BaseModel):
    init_data: str
    tree_id: int


class AnswerRequest(BaseModel):
    init_data: str
    answer: List[str]


def loot_text(loot):
    return ", ".join(NAMES.get(i, i) + " x" + str(q) for i, q in loot.items())


def best_axe_gap(tid):
    rows = (
        supabase.table("inventory")
        .select("item_id")
        .eq("telegram_id", tid)
        .in_("item_id", list(AXE_GAP))
        .execute()
        .data
    )
    gaps = [AXE_GAP[r["item_id"]] for r in rows]
    return min(gaps) if gaps else None


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


def tree_view(tree, now, gap):
    started = tree["last"] > 0
    wait = 0.0
    if started and not tree["felled"]:
        wait = max(0.0, gap - (now - tree["last"]))
    return {
        "id": tree["id"], "x": tree["x"], "y": tree["y"],
        "hits": tree["hits"], "felled": tree["felled"],
        "started": started, "wait": round(wait, 1),
    }


def forest_payload(data):
    now = time.time()
    t = data["treasure"]
    return {
        "place": "forest",
        "width": FOREST_W,
        "height": FOREST_H,
        "start": {"x": FOREST_W // 2, "y": FOREST_H - 40},
        "hits_needed": CHOP_HITS,
        "gap": data["gap"],
        "trees": [tree_view(x, now, data["gap"]) for x in data["trees"]],
        "treasure": {"x": t["x"], "y": t["y"], "dug": t["dug"]} if t else None,
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


@router.post("/forest/chop")
@safe
def forest_chop(req: TreeRequest):
    tid = user_id(req.init_data)
    data, ver = load_session(tid, "forest")

    gap = best_axe_gap(tid)
    if gap is None:
        raise HTTPException(400, "Нужен топор. Купи его у торговца")
    data["gap"] = gap

    tree = next((t for t in data["trees"] if t["id"] == req.tree_id), None)
    if tree is None or tree["felled"]:
        raise HTTPException(404, "Это дерево уже срублено")

    now = time.time()
    loot = None

    if tree["last"] == 0:
        tree["last"] = now
        message = "Рубка началась. Нажимай «Рубить» каждые " + str(gap) + " сек"
    else:
        left = gap - (now - tree["last"])
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
        "tree": tree_view(tree, now, gap),
        "message": message,
        "inventory": load_inventory(tid),
        "player": build_player(tid),
    }


@router.post("/forest/dig")
@safe
def forest_dig(req: InitRequest):
    tid = user_id(req.init_data)
    data, ver = load_session(tid, "forest")

    if not has_item(tid, SHOVELS):
        raise HTTPException(400, "Нужна лопата. Купи её у торговца")

    t = data["treasure"]
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
        "player": build_player(tid),
    }


# ---------- озеро ----------

@router.post("/fish/start")
@safe
def fish_start(req: InitRequest):
    tid = user_id(req.init_data)
    data, ver = load_session(tid, "lake")

    if not has_item(tid, RODS):
        raise HTTPException(400, "Нужна удочка. Купи её у торговца")

    now = time.time()
    phase = data["phase"]
    busy = phase == "waiting" or (
        phase == "bite" and now <= data.get("deadline", 0)
    )
    if busy:
        raise HTTPException(400, "Ты уже ловишь рыбу")

    entry = random.choices(FISH, weights=[f[2] for f in FISH])[0]
    seq = [random.choice(DIRS) for _ in range(entry[3])]
    wait = random.randint(WAIT_MIN, WAIT_MAX)

    commit_session(tid, {
        "phase": "waiting",
        "bite_at": now + wait,
        "fish": entry[0],
        "seq": seq,
    }, ver)
    return {"wait": wait}


@router.post("/fish/bite")
@safe
def fish_bite(req: InitRequest):
    tid = user_id(req.init_data)
    data, ver = load_session(tid, "lake")

    if data["phase"] != "waiting":
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
    tid = user_id(req.init_data)
    data, ver = load_session(tid, "lake")

    if data["phase"] != "bite":
        raise HTTPException(400, "Рыба не клюёт")

    success = False
    if time.time() > data["deadline"]:
        message = "Время вышло, рыба сорвалась"
    elif req.answer != data["seq"]:
        message = "Неверно, рыба сорвалась"
    else:
        success = True
        message = "Поймана рыба: " + NAMES[data["fish"]]

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
        "player": build_player(tid),
    }


# ---------- RTP ----------

@router.post("/rtp/roll")
@safe
def rtp_roll(req: InitRequest):
    tid = user_id(req.init_data)

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
        data = {
            "trees": make_trees(),
            "treasure": make_treasure(),
            "gap": best_axe_gap(tid) or DEFAULT_GAP,
        }
        start_session(tid, "forest", data)
        return forest_payload(data)

    start_session(tid, "lake", {"phase": "idle"})
    return {"place": "lake", "phase": "idle", "wait_left": 0}


@router.post("/rtp/current")
@safe
def rtp_current(req: InitRequest):
    tid = user_id(req.init_data)
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
    if s["kind"] == "clearing":
        return clearing_state(tid, s["data"], s["ver"])

    d = s["data"]
    if d["phase"] == "bite":
        # перезашёл посреди мини-игры: рыба сорвалась
        d = {"phase": "idle"}
        commit_session(tid, d, s["ver"])

    wait_left = 0
    if d["phase"] == "waiting":
        wait_left = max(0, int(d["bite_at"] - time.time() + 0.5))
    return {"place": "lake", "phase": d["phase"], "wait_left": wait_left}


@router.post("/rtp/leave")
@safe
def rtp_leave(req: InitRequest):
    tid = user_id(req.init_data)
    clear_session(tid)
    return {"status": "success"}
