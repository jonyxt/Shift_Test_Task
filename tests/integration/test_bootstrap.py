import asyncio

import pytest

from app import schemas
from app.bootstrap_admin import (
    AdminAlreadyInitialized,
    create_initial_admin,
)
from app.database import AsyncSessionLocal, engine


def test_bootstrap_rejects_second_admin():
    async def check():
        try:
            async with AsyncSessionLocal() as session:
                data = schemas.RegisterRequest(
                    username="another_admin",
                    email="another_admin@example.com",
                    password="password123",
                )

                with pytest.raises(AdminAlreadyInitialized):
                    await create_initial_admin(session, data)
        finally:
            await engine.dispose()

    asyncio.run(check())