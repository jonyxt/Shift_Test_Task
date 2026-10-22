import asyncio
import os
import httpx
import pytest
import jwt

from uuid import uuid4
from sqlalchemy import text
from app.config import config
from app.seed_data import seed_initial_data

from app import auth, models, schemas
from app.bootstrap_admin import create_initial_admin
from app.database import AsyncSessionLocal, engine


@pytest.fixture(scope="session")
def prepare_test_database():
    """Очищает и подготавливает тестовую БД перед запуском pytest."""

    # Защита от случайного удаления данных основной БД.
    if (
        os.getenv("ALLOW_TEST_DB_RESET") != "1"
        or config.POSTGRES_DB != "test_db"
        or config.POSTGRES_HOST != "test_db"
    ):
        pytest.fail(
            "Сброс БД запрещён: требуется "
            "ALLOW_TEST_DB_RESET=1, "
            "POSTGRES_DB=test_db и POSTGRES_HOST=test_db"
        )

    async def setup():
        try:
            # 1. Очищаем все таблицы и сбрасываем ID.
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "TRUNCATE TABLE "
                        "bookings, time_windows, rooms, users "
                        "RESTART IDENTITY CASCADE"
                    )
                )

            # 2. Восстанавливаем комнаты и временные слоты.
            async with AsyncSessionLocal() as session:
                await seed_initial_data(session)

            # 3. Создаём тестового администратора.
            data = schemas.RegisterRequest(
                username="test_first_admin",
                password="password123",
                email="test_first_admin@example.com",
            )

            async with AsyncSessionLocal() as session:
                admin_id = await create_initial_admin(
                    session, data
                )

                admin = await session.get(
                    models.User, admin_id
                )

                assert admin is not None
                assert admin.role == models.UserRole.ADMIN
                assert auth.check_password(
                    data.password,
                    admin.hashed_password,
                )

        finally:
            await engine.dispose()

    asyncio.run(setup())

@pytest.fixture
def api_client():
    """HTTP-клиент для интеграционных тестов API."""

    base_url = os.getenv("BASE_URL", "http://app:8000")

    with httpx.Client(
        base_url=base_url,
        timeout=20.0,
    ) as client:
        yield client

@pytest.fixture
def create_test_user(api_client):
    """Фабрика для создания тестовых пользователей."""

    def create(prefix="test_user"):
        username = f"{prefix}_{uuid4().hex[:12]}"
        password = "password123"

        response = api_client.post(
            "/register",
            json={
                "username": username,
                "email": f"{username}@example.com",
                "password": password,
            },
        )

        assert response.status_code == 200, response.text

        user = response.json()

        login_response = api_client.post(
            "/login",
            json={
                "username": username,
                "password": password,
            },
        )

        assert login_response.status_code == 200, login_response.text

        token = login_response.json()["access_token"]

        return user, token

    return create

@pytest.fixture
def registration_payload():
    """Уникальные данные для регистрации пользователя."""

    suffix = uuid4().hex[:12]
    username = f"test_{suffix}"

    return {
        "username": username,
        "email": f"{username}@example.com",
        "password": "password123",
    }


@pytest.fixture
def admin_token(api_client):
    """JWT-токен тестового администратора."""

    response = api_client.post(
        "/login",
        json={
            "username": "test_first_admin",
            "password": "password123",
        },
    )

    assert response.status_code == 200, response.text

    return response.json()["access_token"]

@pytest.fixture
def available_slot(api_client):
    """Фабрика поиска свободного слота."""

    def get_slot(token, date):
        response = api_client.get(
            f"/rooms/available/{date}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200, response.text

        rooms = response.json()["rooms"]
        assert rooms, "Нет доступных комнат"

        for room in rooms:
            slots = room["available_time_windows"]

            if slots:
                return room["id"], slots[0]["id"]

        pytest.fail("Нет свободных временных слотов")

    return get_slot


@pytest.fixture
def create_test_booking(api_client, available_slot):
    """Фабрика создания бронирований через API."""

    def create(token, date):
        room_id, slot_id = available_slot(token, date)

        response = api_client.post(
            "/bookings",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "room_id": room_id,
                "time_window_id": slot_id,
                "date": date,
            },
        )

        assert response.status_code == 200, response.text

        return response.json()

    return create

@pytest.fixture
def signed_jwt():
    """Фабрика создания подписанных JWT для тестов."""

    def create(payload, algorithm=None):
        return jwt.encode(
            payload,
            auth.JWT_SECRET,
            algorithm=algorithm or auth.JWT_ALGORITHM,
        )

    return create