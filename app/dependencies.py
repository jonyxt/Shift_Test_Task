"""Зависимости FastAPI.

Модуль содержит dependency-функции, которые используются в обработчиках
маршрутов для получения общих ресурсов приложения.
"""
from .database import AsyncSessionLocal

async def get_db_session():
    """Предоставляет асинхронную сессию базы данных для одного запроса.

    Сессия создается через AsyncSessionLocal и автоматически закрывается
    после завершения обработки запроса.
    """
    async with AsyncSessionLocal() as session:
        yield session