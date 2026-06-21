import logging
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
import uvicorn

from db.database import get_db
from db.models import Task
from api.schemas import TaskResponse
from api.routes.tasks import router as tasks_router

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api.main")

app = FastAPI(
    title="Browser Agent API",
    version="0.1.0"
)

# CORS middleware allowing all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os

@app.get("/ui", response_class=HTMLResponse)
async def serve_ui():
    ui_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(ui_path) as f:
        return HTMLResponse(content=f.read())

app.include_router(tasks_router, prefix="/tasks")

@app.on_event("startup")
async def startup_event():
    logger.info("Browser Agent API starting up")

@app.get("/")
async def root():
    return {"status": "ok", "version": "0.1.0"}

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"db": "ok"}
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return {"db": "error", "detail": str(e)}

@app.get("/tasks", response_model=list[TaskResponse])
async def get_tasks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Task).order_by(Task.created_at.desc()).limit(20)
    )
    return result.scalars().all()

if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
