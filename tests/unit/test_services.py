import pytest
import datetime as dt

from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app import models, schemas, services


pytestmark = pytest.mark.asyncio


@pytest.fixture
def session():
    """Имитирует асинхронную сессию SQLAlchemy."""

    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()

    return db


# ==========================================
# Транзакции и обработка ошибок БД
# ==========================================

async def test_commit_refresh_success(session):
    """Успешная транзакция сохраняет и обновляет объект."""

    model = MagicMock()

    result = await services.commit_refresh_db(
        model=model,
        error="Conflict",
        session=session,
    )

    assert result is model
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(model)
    session.rollback.assert_not_awaited()


async def test_commit_refresh_integrity_error(session):
    """При IntegrityError выполняется rollback и возвращается 409."""

    session.commit.side_effect = IntegrityError(
        "INSERT",
        {},
        Exception("duplicate key"),
    )

    with pytest.raises(HTTPException) as exc:
        await services.commit_refresh_db(
            model=MagicMock(),
            error="Duplicate user",
            session=session,
        )

    assert exc.value.status_code == 409
    assert exc.value.detail == "Duplicate user"

    session.rollback.assert_awaited_once()
    session.refresh.assert_not_awaited()


# ==========================================
# Поиск объектов
# ==========================================

async def test_get_object_by_id_success(session):
    """Существующий объект возвращается из репозитория."""

    user = models.User(id=15)

    result = MagicMock()
    result.scalar_one_or_none.return_value = user
    session.execute.return_value = result

    found = await services.get_db_object_by_id(
        session, models.User, 15
    )

    assert found is user
    session.execute.assert_awaited_once()


async def test_get_object_by_id_not_found(session):
    """Отсутствующий объект вызывает HTTP 404."""

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    with pytest.raises(HTTPException) as exc:
        await services.get_db_object_by_id(
            session, models.User, 999
        )

    assert exc.value.status_code == 404
    assert "999" in exc.value.detail


# ==========================================
# Авторизация
# ==========================================

async def test_login_success(session, monkeypatch):
    """Верные учётные данные возвращают JWT."""

    user = models.User(
        id=10,
        hashed_password="stored_hash",
    )
    session.scalar.return_value = user

    check_password = MagicMock(return_value=True)
    create_token = MagicMock(return_value="test-jwt")

    monkeypatch.setattr(
        services.auth, "check_password", check_password
    )
    monkeypatch.setattr(
        services.auth, "create_access_token", create_token
    )

    credentials = schemas.LoginRequest(
        username="employee",
        password="password123",
    )

    result = await services.login_user(
        session, credentials
    )

    assert result.access_token == "test-jwt"
    assert result.token_type == "bearer"

    check_password.assert_called_once_with(
        "password123", "stored_hash"
    )
    create_token.assert_called_once_with(user_id=10)


@pytest.mark.parametrize(
    "case",
    ["unknown_user", "wrong_password"],
)
async def test_login_invalid_credentials(
    session, monkeypatch, case
):
    """Неизвестный пользователь и неверный пароль дают 401."""

    if case == "unknown_user":
        session.scalar.return_value = None
    else:
        session.scalar.return_value = models.User(
            id=10,
            hashed_password="stored_hash",
        )

    check_password = MagicMock(return_value=False)
    create_token = MagicMock()

    monkeypatch.setattr(
        services.auth, "check_password", check_password
    )
    monkeypatch.setattr(
        services.auth, "create_access_token", create_token
    )

    credentials = schemas.LoginRequest(
        username="employee",
        password="wrong_password",
    )

    with pytest.raises(HTTPException) as exc:
        await services.login_user(session, credentials)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Неверный логин или пароль"

    create_token.assert_not_called()


# ==========================================
# Создание бронирования
# ==========================================

async def test_booking_past_date(session):
    """Нельзя бронировать прошедшие даты."""

    user = models.User(id=7)

    data = schemas.CreateBookingRequest(
        room_id=1,
        time_window_id=2,
        date=dt.date.today() - dt.timedelta(days=1),
    )

    with pytest.raises(HTTPException) as exc:
        await services.book_room(session, user, data)

    assert exc.value.status_code == 400
    session.scalar.assert_not_awaited()
    session.add.assert_not_called()


async def test_booking_invalid_slot(session):
    """Неверный, чужой или недоступный слот отклоняется."""

    user = models.User(id=7)
    session.scalar.return_value = None

    data = schemas.CreateBookingRequest(
        room_id=1,
        time_window_id=999,
        date=dt.date.today() + dt.timedelta(days=1),
    )

    with pytest.raises(HTTPException) as exc:
        await services.book_room(session, user, data)

    assert exc.value.status_code == 400
    session.add.assert_not_called()


async def test_booking_success(session, monkeypatch):
    """Корректное бронирование передаётся на сохранение."""

    user = models.User(id=7)
    session.scalar.return_value = object()

    commit_mock = AsyncMock(
        side_effect=lambda **kwargs: kwargs["model"]
    )

    monkeypatch.setattr(
        services, "commit_refresh_db", commit_mock
    )

    booking_date = dt.date.today() + dt.timedelta(days=1)

    data = schemas.CreateBookingRequest(
        room_id=2,
        time_window_id=3,
        date=booking_date,
    )

    booking = await services.book_room(
        session, user, data
    )

    assert isinstance(booking, models.Booking)
    assert booking.owner_id == 7
    assert booking.room_id == 2
    assert booking.time_window_id == 3
    assert booking.date == booking_date

    session.add.assert_called_once_with(booking)
    commit_mock.assert_awaited_once()


# ==========================================
# Права доступа к бронированиям
# ==========================================

async def test_booking_info_forbidden(
    session, monkeypatch
):
    """Сотрудник не может просмотреть чужую бронь."""

    user = models.User(
        id=7, role=models.UserRole.EMPLOYEE
    )
    booking = models.Booking(id=20, owner_id=8)

    monkeypatch.setattr(
        services,
        "get_db_object_by_id",
        AsyncMock(return_value=booking),
    )

    with pytest.raises(HTTPException) as exc:
        await services.book_room_info(
            session, user, booking_id=20
        )

    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "role,owner_id",
    [
        (models.UserRole.EMPLOYEE, 7),
        (models.UserRole.ADMIN, 8),
    ],
)
async def test_booking_info_allowed(
    session, monkeypatch, role, owner_id
):
    """Владелец и администратор получают разрешённую бронь."""

    user = models.User(id=7, role=role)
    booking = models.Booking(id=20, owner_id=owner_id)

    monkeypatch.setattr(
        services,
        "get_db_object_by_id",
        AsyncMock(return_value=booking),
    )

    result = await services.book_room_info(
        session, user, booking_id=20
    )

    assert result is booking


# ==========================================
# Отмена бронирований
# ==========================================

async def test_cancel_other_user_booking_forbidden(
    session, monkeypatch
):
    """Сотрудник не может отменить чужую бронь."""

    user = models.User(
        id=7, role=models.UserRole.EMPLOYEE
    )
    booking = models.Booking(
        id=20, owner_id=8, is_active=True
    )

    monkeypatch.setattr(
        services,
        "get_db_object_by_id",
        AsyncMock(return_value=booking),
    )

    with pytest.raises(HTTPException) as exc:
        await services.book_room_cancel(
            session, user, booking_id=20
        )

    assert exc.value.status_code == 403
    assert booking.is_active is True
    session.commit.assert_not_awaited()


async def test_cancel_already_cancelled_booking(
    session, monkeypatch
):
    """Повторная отмена отклоняется."""

    user = models.User(
        id=7, role=models.UserRole.EMPLOYEE
    )
    booking = models.Booking(
        id=20, owner_id=7, is_active=False
    )

    monkeypatch.setattr(
        services,
        "get_db_object_by_id",
        AsyncMock(return_value=booking),
    )

    with pytest.raises(HTTPException) as exc:
        await services.book_room_cancel(
            session, user, booking_id=20
        )

    assert exc.value.status_code == 400
    session.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "role,user_id,owner_id",
    [
        (models.UserRole.EMPLOYEE, 7, 7),
        (models.UserRole.ADMIN, 9, 7),
    ],
)
async def test_cancel_booking_success(
    session, monkeypatch, role, user_id, owner_id
):
    """Владелец и администратор могут отменять бронь."""

    user = models.User(id=user_id, role=role)
    booking = models.Booking(
        id=20,
        owner_id=owner_id,
        is_active=True,
    )

    monkeypatch.setattr(
        services,
        "get_db_object_by_id",
        AsyncMock(return_value=booking),
    )

    result = await services.book_room_cancel(
        session, user, booking_id=20
    )

    assert result["status"] == "Бронирование отменено"
    assert booking.is_active is False
    assert booking.cancelled_by_id == user_id
    assert booking.cancelled_at is not None
    assert booking.cancelled_at.tzinfo is not None

    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(booking)


# ==========================================
# Управление пользователями
# ==========================================

async def test_employee_cannot_change_own_role(
    session, monkeypatch
):
    """Сотрудник не может повысить себя до администратора."""

    user = models.User(
        id=7, role=models.UserRole.EMPLOYEE
    )

    monkeypatch.setattr(
        services,
        "get_db_object_by_id",
        AsyncMock(return_value=user),
    )

    data = schemas.UpdateUserRequest(
        role=models.UserRole.ADMIN
    )

    with pytest.raises(HTTPException) as exc:
        await services.update_user_by_id(
            session, 7, data, user
        )

    assert exc.value.status_code == 403
    assert user.role == models.UserRole.EMPLOYEE


async def test_employee_cannot_update_other_user(
    session, monkeypatch
):
    """Сотрудник не может изменять чужой профиль."""

    current_user = models.User(
        id=7, role=models.UserRole.EMPLOYEE
    )
    other_user = models.User(
        id=8, role=models.UserRole.EMPLOYEE
    )

    monkeypatch.setattr(
        services,
        "get_db_object_by_id",
        AsyncMock(return_value=other_user),
    )

    data = schemas.UpdateUserRequest(
        phone="79998887766"
    )

    with pytest.raises(HTTPException) as exc:
        await services.update_user_by_id(
            session, 8, data, current_user
        )

    assert exc.value.status_code == 403
    session.commit.assert_not_awaited()


async def test_cannot_demote_last_admin(
    session, monkeypatch
):
    """Последнего администратора нельзя понизить."""

    admin = models.User(
        id=1, role=models.UserRole.ADMIN
    )

    session.scalar.return_value = 1

    monkeypatch.setattr(
        services,
        "get_db_object_by_id",
        AsyncMock(return_value=admin),
    )

    data = schemas.UpdateUserRequest(
        role=models.UserRole.EMPLOYEE
    )

    with pytest.raises(HTTPException) as exc:
        await services.update_user_by_id(
            session, 1, data, admin
        )

    assert exc.value.status_code == 400
    assert admin.role == models.UserRole.ADMIN
    session.commit.assert_not_awaited()


# ==========================================
# Формирование доступных комнат
# ==========================================

async def test_available_rooms_grouped_correctly(session):
    """Свободные слоты группируются по комнатам."""

    room_1 = models.Room(
        id=1,
        room_name="Room A",
        description="First",
    )
    room_2 = models.Room(
        id=2,
        room_name="Room B",
        description="Second",
    )

    slot_1 = models.TimeWindow(
        id=11,
        room_id=1,
        start_time=dt.time(9, 0),
        end_time=dt.time(12, 0),
    )
    slot_2 = models.TimeWindow(
        id=12,
        room_id=1,
        start_time=dt.time(13, 0),
        end_time=dt.time(16, 0),
    )
    slot_3 = models.TimeWindow(
        id=21,
        room_id=2,
        start_time=dt.time(9, 0),
        end_time=dt.time(12, 0),
    )

    db_result = MagicMock()
    db_result.all.return_value = [
        (room_1, slot_1),
        (room_1, slot_2),
        (room_2, slot_3),
    ]
    session.execute.return_value = db_result

    result = await services.get_date_available_bookings(
        session,
        dt.date.today() + dt.timedelta(days=1),
    )

    rooms = result["rooms"]

    assert len(rooms) == 2

    assert rooms[0]["id"] == 1
    assert rooms[0]["room_name"] == "Room A"
    assert [
        slot["id"]
        for slot in rooms[0]["available_time_windows"]
    ] == [11, 12]

    assert rooms[1]["id"] == 2
    assert [
        slot["id"]
        for slot in rooms[1]["available_time_windows"]
    ] == [21]

    session.execute.assert_awaited_once()
