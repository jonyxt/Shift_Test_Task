"""Тесты: test_booking_security."""


import httpx
import datetime
import pytest
import asyncio
from sqlalchemy import delete
from app import models
from app.config import config
from app.database import AsyncSessionLocal, engine
from tests.integration.helpers import BASE_URL, auth_headers, future_date


def test_employee_cannot_get_other_user_booking_by_id(
    api_client, create_test_user, create_test_booking
):
    """Сотрудник не может прочитать чужое бронирование."""

    _, token_1 = create_test_user()
    _, token_2 = create_test_user()

    booking = create_test_booking(token_1, future_date(5))

    response = api_client.get(
        f"/bookings/{booking['id']}",
        headers=auth_headers(token_2),
    )

    assert response.status_code == 403


def test_employee_cannot_cancel_other_user_booking(
    api_client, create_test_user, create_test_booking
):
    """Сотрудник не может отменить чужое бронирование."""

    _, token_1 = create_test_user()
    _, token_2 = create_test_user()

    booking = create_test_booking(token_1, future_date(7))

    response = api_client.patch(
        f"/bookings/cancel/{booking['id']}",
        headers=auth_headers(token_2),
    )

    assert response.status_code == 403

    booking_response = api_client.get(
        f"/bookings/{booking['id']}",
        headers=auth_headers(token_1),
    )

    assert booking_response.status_code == 200
    assert booking_response.json()["is_active"] is True


def test_user_cannot_book_already_booked_slot(
    api_client, create_test_user, available_slot
):
    """Два пользователя не могут занять один слот."""

    _, token_1 = create_test_user()
    _, token_2 = create_test_user()

    date = future_date(8)
    room_id, slot_id = available_slot(token_1, date)

    payload = {
        "room_id": room_id,
        "time_window_id": slot_id,
        "date": date,
    }

    first_response = api_client.post(
        "/bookings",
        headers=auth_headers(token_1),
        json=payload,
    )

    assert first_response.status_code == 200

    second_response = api_client.post(
        "/bookings",
        headers=auth_headers(token_2),
        json=payload,
    )

    assert second_response.status_code == 409


def test_employee_cannot_get_all_bookings(
    api_client, create_test_user
):
    """Сотрудник не может получить все бронирования."""

    _, token = create_test_user()

    response = api_client.get(
        "/bookings/all",
        headers=auth_headers(token),
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    "field,invalid_id",
    [
        ("room_id", -1),
        ("room_id", 999999999),
        ("time_window_id", -1),
        ("time_window_id", 999999999),
    ],
)
def test_booking_invalid_references(
    api_client, admin_token, available_slot,
    field, invalid_id
):
    """Некорректные ссылки на комнату и слот отклоняются."""

    date = future_date(100)

    room_id, slot_id = available_slot(
        admin_token, date
    )

    payload = {
        "room_id": room_id,
        "time_window_id": slot_id,
        "date": date,
    }

    payload[field] = invalid_id

    response = api_client.post(
        "/bookings",
        headers=auth_headers(admin_token),
        json=payload,
    )

    assert response.status_code == 400


def test_booking_slot_from_another_room(
    api_client, admin_token, available_slot
):
    """Нельзя забронировать слот от другой комнаты."""

    date = future_date(101)
    headers = auth_headers(admin_token)

    room_id, slot_id = available_slot(
        admin_token, date
    )

    rooms_response = api_client.get(
        "/rooms",
        headers=headers,
    )

    assert rooms_response.status_code == 200

    rooms = rooms_response.json()["rooms"]

    other_rooms = [
        room for room in rooms
        if room["id"] != room_id
    ]

    assert other_rooms, "Нужна минимум вторая комната"

    response = api_client.post(
        "/bookings",
        headers=headers,
        json={
            "room_id": other_rooms[0]["id"],
            "time_window_id": slot_id,
            "date": date,
        },
    )

    assert response.status_code == 400


def test_inactive_room_cannot_be_booked(admin_token):
    """Неактивная комната недоступна для бронирования."""

    assert config.POSTGRES_DB == "test_db"
    assert config.POSTGRES_HOST == "test_db"

    token = admin_token
    date = future_date(120)

    async def scenario():
        # Создаём отдельную неактивную комнату
        async with AsyncSessionLocal() as session:
            room = models.Room(
                room_name="Inactive test room",
                description="Security test",
                is_active=False,
            )
            session.add(room)
            await session.flush()

            slot = models.TimeWindow(
                room_id=room.id,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(12, 0),
            )
            session.add(slot)
            await session.flush()

            room_id = room.id
            slot_id = slot.id

            await session.commit()

        try:
            # Неактивная комната не должна
            # присутствовать среди доступных
            response = httpx.get(
                f"{BASE_URL}/rooms/available/{date}",
                headers=auth_headers(token),
            )

            assert response.status_code == 200

            available_room_ids = [
                item["id"]
                for item in response.json()["rooms"]
            ]

            assert room_id not in available_room_ids

            # Прямой запрос на бронирование
            # также должен быть отклонён
            response = httpx.post(
                f"{BASE_URL}/bookings",
                headers=auth_headers(token),
                json={
                    "room_id": room_id,
                    "time_window_id": slot_id,
                    "date": date,
                },
            )

            assert response.status_code == 400

        finally:
            # Удаляем только созданные тестом записи
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(models.Booking).where(
                        models.Booking.room_id == room_id
                    )
                )

                await session.execute(
                    delete(models.TimeWindow).where(
                        models.TimeWindow.id == slot_id
                    )
                )

                await session.execute(
                    delete(models.Room).where(
                        models.Room.id == room_id
                    )
                )

                await session.commit()


    async def run_with_disposal():
        try:
            await scenario()
        finally:
            await engine.dispose()

    asyncio.run(run_with_disposal())
