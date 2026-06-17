"""
PR Review Agent — FastAPI entry point.

Endpoints:
  POST /webhook/github  — receives GitHub webhook events
  GET  /health          — health check
"""
import structlog
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from core.config import get_settings
from github.webhook import router as webhook_router
from db.database import init_db

# Configure structured logging
logging.basicConfig(level=get_settings().log_level)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", env=get_settings().app_env)
    await init_db()
    yield
    log.info("shutdown")


app = FastAPI(
    title="PR Review Agent",
    description="AI-powered GitHub PR reviewer",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(webhook_router, prefix="/webhook")


@app.get("/health")
async def health():
    return {"status": "ok"}
