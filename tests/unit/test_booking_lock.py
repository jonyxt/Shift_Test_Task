from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app import models, services


@pytest.mark.asyncio
async def test_cancel_locks_booking_row_before_reading(monkeypatch):
    """При отмене строка брони блокируется FOR UPDATE до чтения её статуса."""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    owner = models.User(id=11, role=models.UserRole.EMPLOYEE)
    booking = models.Booking(id=5, owner_id=11, is_active=True)
    find_booking = AsyncMock(return_value=booking)
    monkeypatch.setattr(services, "get_db_object_by_id", find_booking)

    result = await services.book_room_cancel(session, owner, booking_id=5)

    assert result["status"] == "Бронирование отменено"
    session.execute.assert_awaited_once()
    locking_query = session.execute.await_args.args[0]
    sql = str(locking_query.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql
    assert "FROM bookings" in sql
    find_booking.assert_awaited_once_with(session, models.Booking, 5)
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(booking)
