"""Жизненный цикл FastAPI-приложения."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Закрывает соединения с БД при остановке приложения."""

    try:
        yield
    finally:
        await engine.dispose()
