
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app import models, schemas, services


pytestmark = pytest.mark.asyncio


@pytest.fixture
def session():
    db = MagicMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


def mock_query_results(session, items):
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = items
    session.execute.return_value = result


async def test_get_self_returns_same_user():
    user = models.User(id=7)
    assert services.get_self(user) is user


async def test_get_users_returns_query_results(session):
    users = [models.User(id=1), models.User(id=2)]
    mock_query_results(session, users)

    result = await services.get_users(session)

    assert result["users"] == users
    session.execute.assert_awaited_once()


async def test_get_all_rooms_info(session):
    rooms = [models.Room(id=1), models.Room(id=2)]
    mock_query_results(session, rooms)

    result = await services.get_all_rooms_info(session)

    assert result["rooms"] == rooms


@pytest.mark.parametrize("filter_by_date", [False, True])
async def test_get_all_bookings(session, filter_by_date):
    import datetime

    bookings = [models.Booking(id=5)]
    mock_query_results(session, bookings)

    date = datetime.date(2027, 1, 15) if filter_by_date else None

    result = await services.get_all_bookings(session, date)

    assert result["bookings"] == bookings
    session.execute.assert_awaited_once()


async def test_get_all_user_bookings(session):
    user = models.User(id=7)
    bookings = [models.Booking(id=12, owner_id=7)]
    mock_query_results(session, bookings)

    result = await services.get_all_user_bookings(
        session, user
    )

    assert result["bookings"] == bookings
    session.execute.assert_awaited_once()


async def test_available_rooms_empty(session):
    import datetime

    result = MagicMock()
    result.all.return_value = []
    session.execute.return_value = result

    data = await services.get_date_available_bookings(
        session, datetime.date(2027, 1, 15)
    )

    assert data == {"rooms": []}


async def test_employee_updates_own_phone(session, monkeypatch):
    user = models.User(
        id=7,
        role=models.UserRole.EMPLOYEE,
    )

    monkeypatch.setattr(
        services,
        "get_db_object_by_id",
        AsyncMock(return_value=user),
    )

    save = AsyncMock(
        side_effect=lambda **kwargs: kwargs["model"]
    )
    monkeypatch.setattr(services, "commit_refresh_db", save)

    data = schemas.UpdateUserRequest(phone="79991112233")

    result = await services.update_user_by_id(
        session, 7, data, user
    )

    assert result is user
    assert user.phone == "79991112233"
    save.assert_awaited_once()


async def test_admin_promotes_another_user(session, monkeypatch):
    admin = models.User(id=1, role=models.UserRole.ADMIN)
    employee = models.User(
        id=7, role=models.UserRole.EMPLOYEE
    )

    monkeypatch.setattr(
        services,
        "get_db_object_by_id",
        AsyncMock(return_value=employee),
    )

    save = AsyncMock(
        side_effect=lambda **kwargs: kwargs["model"]
    )
    monkeypatch.setattr(services, "commit_refresh_db", save)

    data = schemas.UpdateUserRequest(
        role=models.UserRole.ADMIN
    )

    result = await services.update_user_by_id(
        session, 7, data, admin
    )

    assert result.role == models.UserRole.ADMIN
    save.assert_awaited_once()


async def test_admin_demotes_when_multiple_admins(
    session, monkeypatch
):
    admin = models.User(id=1, role=models.UserRole.ADMIN)
    target = models.User(id=2, role=models.UserRole.ADMIN)

    session.scalar.return_value = 2

    monkeypatch.setattr(
        services,
        "get_db_object_by_id",
        AsyncMock(return_value=target),
    )

    save = AsyncMock(
        side_effect=lambda **kwargs: kwargs["model"]
    )
    monkeypatch.setattr(services, "commit_refresh_db", save)

    data = schemas.UpdateUserRequest(
        role=models.UserRole.EMPLOYEE
    )

    result = await services.update_user_by_id(
        session, 2, data, admin
    )

    assert result.role == models.UserRole.EMPLOYEE
    session.scalar.assert_awaited_once()
    save.assert_awaited_once()


@pytest.mark.parametrize(
    "field",
    ["username", "email", "role"],
)
async def test_admin_rejects_null_fields(
    session, monkeypatch, field
):
    admin = models.User(id=1, role=models.UserRole.ADMIN)
    target = models.User(id=2, role=models.UserRole.EMPLOYEE)

    monkeypatch.setattr(
        services,
        "get_db_object_by_id",
        AsyncMock(return_value=target),
    )

    data = schemas.UpdateUserRequest(**{field: None})

    with pytest.raises(HTTPException) as exc:
        await services.update_user_by_id(
            session, 2, data, admin
        )

    assert exc.value.status_code == 422
    session.commit.assert_not_awaited()
