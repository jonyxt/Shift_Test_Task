"""Тесты: test_errors."""


import pytest
from uuid import uuid4
from tests.integration.helpers import auth_headers, future_date


@pytest.mark.parametrize(
    "field",
    ["username", "email", "phone"],
)
def test_duplicate_registration_returns_409(
    api_client, registration_payload, field
):
    """Конфликт уникальности возвращает HTTP 409."""

    first = {
        **registration_payload,
        "phone": None,
    }

    suffix = uuid4().hex[:12]
    second = {
        "username": f"test_second_{suffix}",
        "email": f"second_{suffix}@example.com",
        "password": "password123",
        "phone": None,
    }

    if field == "phone":
        phone = f"79{uuid4().int % 10**9:09d}"
        first["phone"] = phone
        second["phone"] = phone
    else:
        second[field] = first[field]

    first_response = api_client.post(
        "/register",
        json=first,
    )

    assert first_response.status_code == 200

    response = api_client.post(
        "/register",
        json=second,
    )

    assert response.status_code == 409
    assert "detail" in response.json()

    detail = str(response.json()["detail"]).lower()

    for forbidden in (
        "sqlalchemy",
        "asyncpg",
        "duplicate key",
        "insert into",
        "traceback",
    ):
        assert forbidden not in detail

    # Проверяем работоспособность после ошибки.
    suffix = uuid4().hex[:12]

    valid_response = api_client.post(
        "/register",
        json={
            "username": f"test_recovery_{suffix}",
            "email": f"recovery_{suffix}@example.com",
            "password": "password123",
        },
    )

    assert valid_response.status_code == 200


@pytest.mark.parametrize(
    "field",
    ["username", "email"],
)
def test_conflicting_profile_update_preserves_data(
    api_client, create_test_user, field
):
    """Неудачное обновление не изменяет данные пользователя."""

    user_1, _ = create_test_user()
    user_2, token_2 = create_test_user()

    headers = auth_headers(token_2)

    response = api_client.patch(
        f"/users/{user_2['id']}",
        headers=headers,
        json={field: user_1[field]},
    )

    assert response.status_code == 409

    profile_response = api_client.get(
        "/users/self",
        headers=headers,
    )

    assert profile_response.status_code == 200
    assert profile_response.json()[field] == user_2[field]


def test_cannot_cancel_booking_twice(
    api_client, create_test_user, create_test_booking
):
    """Повторная отмена бронирования отклоняется."""

    _, token = create_test_user()
    booking = create_test_booking(token, future_date(70))

    endpoint = f"/bookings/cancel/{booking['id']}"
    headers = auth_headers(token)

    first_response = api_client.patch(
        endpoint,
        headers=headers,
    )

    assert first_response.status_code == 200

    second_response = api_client.patch(
        endpoint,
        headers=headers,
    )

    assert second_response.status_code == 400

    response = api_client.get(
        f"/bookings/{booking['id']}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/users/99999999"),
        ("GET", "/rooms/99999999"),
        ("GET", "/bookings/99999999"),
        ("PATCH", "/bookings/cancel/99999999"),
    ],
)
def test_nonexistent_objects_return_404(
    api_client, admin_token, method, path
):
    """Несуществующий объект возвращает HTTP 404."""

    response = api_client.request(
        method,
        path,
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 404
    assert "detail" in response.json()
