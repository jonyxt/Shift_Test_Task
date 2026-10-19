"""Подготовка тестового администратора."""

import asyncio

import pytest
from sqlalchemy import select

from app import auth, models, schemas
from app.bootstrap_admin import (
    AdminAlreadyInitialized,
    create_initial_admin,
)
from app.database import AsyncSessionLocal, engine


@pytest.fixture(scope="session", autouse=True)
def bootstrap_test_admin():
    async def setup():
        try:
            async with AsyncSessionLocal() as session:
                data = schemas.RegisterRequest(
                    username="test_first_admin",
                    password="password123",
                    email="test_first_admin@example.com",
                )

                try:
                    admin_id = await create_initial_admin(
                        session, data
                    )
                    admin = await session.get(
                        models.User, admin_id
                    )

                except AdminAlreadyInitialized:
                    admin = await session.scalar(
                        select(models.User).where(
                            models.User.username
                            == "test_first_admin"
                        )
                    )

                assert admin is not None
                assert admin.role == models.UserRole.ADMIN
                assert auth.check_password(
                    data.password, admin.hashed_password
                )
        finally:
            await engine.dispose()

    asyncio.run(setup())
