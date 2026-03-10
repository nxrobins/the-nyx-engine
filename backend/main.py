"""Nyx Engine - Application Entry Point."""

import logging
import os
from contextlib import asynccontextmanager

import uvicorn

# Fix pydantic-settings priority: empty shell env vars override .env values.
# Remove empty API key env vars so .env takes precedence.
for _key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "MERCURY_API_KEY"):
    if os.environ.get(_key, None) == "":
        del os.environ[_key]
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.db import init_pool, close_pool

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(name)-12s | %(levelname)-7s | %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle: DB pool management."""
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title=settings.app_name,
    description="Multi-agent CYOA game engine governed by the Children of Nyx.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://10.0.0.82:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    return {
        "engine": "Nyx",
        "version": "0.1.0",
        "status": "The thread awaits.",
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
