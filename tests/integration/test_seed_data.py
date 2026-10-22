
"""Проверка повторной инициализации начальных данных."""

import pytest
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models import Room, TimeWindow
from app.seed_data import seed_initial_data


@pytest.mark.asyncio
async def test_seed_is_idempotent():
    """Повторная инициализация не создаёт дубликаты."""

    # Запускаем инициализацию дважды.
    for _ in range(2):
        async with AsyncSessionLocal() as session:
            await seed_initial_data(session)

    # Проверяем результат в тестовой БД.
    async with AsyncSessionLocal() as session:
        rooms_count = await session.scalar(
            select(func.count()).select_from(Room)
        )
        slots_count = await session.scalar(
            select(func.count()).select_from(TimeWindow)
        )

    assert rooms_count == 3
    assert slots_count == 9
