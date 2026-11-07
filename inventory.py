from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import (
    INVENTORY_SIZE,
    change_balance,
    safe,
    supabase,
    user_id,
)
from progress import award_loot_xp, build_player

router = APIRouter()

STARTER_ITEMS = ["wooden_sword", "leather_helmet", "bandage", "bandage"]
SHOP_CATEGORIES = ["pvp", "mine", "other"]


class ItemRequest(BaseModel):
    init_data: str
    inv_id: int


class BuyRequest(BaseModel):
    init_data: str
    item_id: str


# ---------- помощники ----------

def load_inventory(tid: int):
    return (
        supabase.table("inventory")
        .select("id,equipped,qty,items(id,name,type,slot,rarity,sell_price)")
        .eq("telegram_id", tid)
        .order("id")
        .execute()
        .data
    )


def bag_rows(tid: int):
    """Предметы в сумке. Надетые вещи слоты сумки не занимают."""
    return (
        supabase.table("inventory")
        .select("id,item_id,qty")
        .eq("telegram_id", tid)
        .eq("equipped", False)
        .execute()
        .data
    )


def has_item(tid: int, item_ids):
    r = (
        supabase.table("inventory")
        .select("id")
        .eq("telegram_id", tid)
        .in_("item_id", list(item_ids))
        .limit(1)
        .execute()
    )
    return bool(r.data)


def check_space(tid: int, loot: dict):
    rows = bag_rows(tid)
    have = {r["item_id"] for r in rows}
    new_slots = len([i for i in loot if i not in have])
    if len(rows) + new_slots > INVENTORY_SIZE:
        raise HTTPException(400, "Инвентарь полон. Продай что-нибудь торговцу")


def add_items(tid: int, loot: dict):
    """Добавляет ресурсы (одинаковые складываются в стопку) и даёт опыт."""
    check_space(tid, loot)
    have = {}
    for r in bag_rows(tid):
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

    award_loot_xp(tid, loot)


def give_starter_items(tid: int):
    claim = (
        supabase.table("players")
        .update({"starter_given": True})
        .eq("telegram_id", tid)
        .eq("starter_given", False)
        .execute()
    )
    if not claim.data:
        return

    supabase.table("inventory").insert(
        [{"telegram_id": tid, "item_id": i} for i in STARTER_ITEMS]
    ).execute()


def own_row(tid: int, inv_id: int):
    r = (
        supabase.table("inventory")
        .select("id,equipped,qty,items(name,type,slot,sell_price)")
        .eq("id", inv_id)
        .eq("telegram_id", tid)
        .limit(1)
        .execute()
    )
    if not r.data:
        raise HTTPException(404, "Предмет не найден")
    return r.data[0]


# ---------- инвентарь ----------

@router.post("/inventory/equip")
@safe
def equip(req: ItemRequest):
    tid = user_id(req.init_data)
    row = own_row(tid, req.inv_id)
    slot = (row.get("items") or {}).get("slot")

    if not slot:
        raise HTTPException(400, "Этот предмет нельзя надеть")

    # то, что надето в этом слоте, уходит в сумку
    same_slot = (
        supabase.table("inventory")
        .select("id,items!inner(slot)")
        .eq("telegram_id", tid)
        .eq("equipped", True)
        .eq("items.slot", slot)
        .execute()
        .data
    )
    for old in same_slot:
        supabase.table("inventory").update(
            {"equipped": False}
        ).eq("id", old["id"]).execute()

    supabase.table("inventory").update(
        {"equipped": True}
    ).eq("id", req.inv_id).eq("telegram_id", tid).execute()

    return {"inventory": load_inventory(tid), "player": build_player(tid)}


@router.post("/inventory/unequip")
@safe
def unequip(req: ItemRequest):
    tid = user_id(req.init_data)
    row = own_row(tid, req.inv_id)

    if row["equipped"] and len(bag_rows(tid)) >= INVENTORY_SIZE:
        raise HTTPException(400, "Инвентарь полон, снять некуда")

    supabase.table("inventory").update(
        {"equipped": False}
    ).eq("id", req.inv_id).eq("telegram_id", tid).execute()

    return {"inventory": load_inventory(tid), "player": build_player(tid)}


@router.post("/inventory/delete")
@safe
def inventory_delete(req: ItemRequest):
    tid = user_id(req.init_data)
    row = own_row(tid, req.inv_id)

    if row["equipped"]:
        raise HTTPException(400, "Сначала сними предмет")

    supabase.table("inventory").delete().eq(
        "id", req.inv_id
    ).eq("telegram_id", tid).execute()

    return {"message": "Предмет удалён", "inventory": load_inventory(tid)}


@router.get("/items/catalog")
@safe
def items_catalog():
    rows = (
        supabase.table("items")
        .select("id,name,type,slot,rarity,damage,armor,hp_bonus,heal")
        .execute()
        .data
    )
    return {"items": {i["id"]: i for i in rows}}


# ---------- магазин ----------

@router.get("/shop/items")
@safe
def shop_items():
    rows = (
        supabase.table("items")
        .select("id,name,type,slot,rarity,price,shop_category")
        .in_("shop_category", SHOP_CATEGORIES)
        .order("shop_order")
        .order("price")
        .execute()
        .data
    )
    return {"items": rows}


@router.post("/shop/buy")
@safe
def shop_buy(req: BuyRequest):
    tid = user_id(req.init_data)

    found = (
        supabase.table("items")
        .select("id,name,price")
        .eq("id", req.item_id)
        .in_("shop_category", SHOP_CATEGORIES)
        .limit(1)
        .execute()
        .data
    )
    if not found:
        raise HTTPException(404, "Этого предмета нет в магазине")
    item = found[0]

    if len(bag_rows(tid)) >= INVENTORY_SIZE:
        raise HTTPException(400, "Инвентарь полон")

    change_balance(tid, -item["price"])
    try:
        supabase.table("inventory").insert(
            {"telegram_id": tid, "item_id": item["id"]}
        ).execute()
    except Exception:
        change_balance(tid, item["price"])
        raise

    return {
        "message": "Куплено: " + item["name"],
        "player": build_player(tid),
        "inventory": load_inventory(tid),
    }


@router.post("/shop/sell")
@safe
def shop_sell(req: ItemRequest):
    tid = user_id(req.init_data)
    row = own_row(tid, req.inv_id)
    item = row["items"]

    if item["type"] != "resource" or row["equipped"]:
        raise HTTPException(400, "NPC покупает только ресурсы")

    total = item["sell_price"] * row["qty"]

    deleted = (
        supabase.table("inventory")
        .delete()
        .eq("id", req.inv_id)
        .eq("telegram_id", tid)
        .execute()
    )
    if not deleted.data:
        raise HTTPException(404, "Предмет уже продан")

    change_balance(tid, total)

    return {
        "message": "Продано: " + item["name"] + " x" + str(row["qty"])
                   + " (+" + str(total) + ")",
        "player": build_player(tid),
        "inventory": load_inventory(tid),
      }
