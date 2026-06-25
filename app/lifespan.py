"""Жизненный цикл FastAPI-приложения.

Модуль описывает действия при старте и остановке приложения: создание таблиц,
инициализацию стартовых переговорных комнат и временных слотов, а также
корректное закрытие соединений с базой данных.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI


from .services import initial_rooms_and_time_windows
from .database import engine, Base, AsyncSessionLocal


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управляет стартом и завершением приложения.

    При запуске создает таблицы ORM-моделей и добавляет начальные комнаты
    со слотами, если они еще не были созданы. При завершении закрывает engine.
    """
    print('Starting up...')
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncSessionLocal() as session:
        await initial_rooms_and_time_windows(session)
    yield
    print('Shutting down...')
    await engine.dispose()