from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from combat import router as combat_router
from core import InitRequest, safe, supabase, verify_telegram_data
from inventory import give_starter_items, load_inventory
from inventory import router as inventory_router
from progress import build_player
from progress import router as progress_router
from rtp import router as rtp_router

app = FastAPI(title="My Game API")

app.include_router(progress_router)
app.include_router(inventory_router)
app.include_router(rtp_router)
app.include_router(combat_router)

NO_CACHE = {"Cache-Control": "no-store"}
JS_FILES = ("ui.js", "world.js", "fight.js")


@app.get("/")
def home():
    return FileResponse("static/index.html", headers=NO_CACHE)


@app.get("/js/{name}")
def js_file(name: str):
    if name not in JS_FILES:
        raise HTTPException(404, "Not found")
    return FileResponse(
        "static/" + name,
        media_type="application/javascript",
        headers=NO_CACHE,
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
@safe
def telegram_auth(req: InitRequest):
    user = verify_telegram_data(req.init_data)
    tid = user["id"]

    supabase.table("players").upsert(
        {
            "telegram_id": tid,
            "username": user.get("username"),
            "first_name": user.get("first_name", ""),
            "photo_url": user.get("photo_url"),
        },
        on_conflict="telegram_id",
    ).execute()
    give_starter_items(tid)

    return {
        "status": "success",
        "player": build_player(tid),
        "inventory": load_inventory(tid),
    }
