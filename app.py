from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from api.chat import router as chat_router
from api.experiments import router as experiments_router
from api.memories import router as memories_router
from api.tts import router as tts_router
from config import BASE_DIR
from database.db import initialize_database
from scheduler import start_daily_scheduler

app = FastAPI(title="实验助手 API", version="0.8.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "frontend"), name="static")


@app.on_event("startup")
def startup():
    initialize_database()
    start_daily_scheduler()


@app.get("/", include_in_schema=False)
def home():
    page = (BASE_DIR / "frontend" / "index.html").read_text(encoding="utf-8")
    scripts = '<script src="/static/experiment_confirmation.js"></script><script src="/static/experiment_status.js"></script><script src="/static/history_panel.js"></script><script src="/static/memory_panel.js"></script><script src="/static/conversation.js"></script>'
    return HTMLResponse(page.replace("</body>", scripts + "</body>"))


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(chat_router)
app.include_router(experiments_router)
app.include_router(memories_router)
app.include_router(tts_router)
