from fastapi import FastAPI

app = FastAPI(title="My Game API")


@app.get("/")
def home():
    return {
        "status": "online",
        "message": "Game server is working!"
    }


@app.get("/health")
def health():
    return {"ok": True}
