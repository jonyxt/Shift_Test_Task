"""Тесты: test_validation."""


import datetime
import pytest
from tests.integration.helpers import auth_headers, future_date


@pytest.mark.parametrize(
    "case_id, changes",
    [
        ("name_short", {"username": "abc"}),
        ("password_short", {"password": "1234567"}),
        ("email_bad", {"email": "not-an-email"}),
        ("phone_long", {"phone": "7" * 13}),
    ],
)
def test_registration_invalid_data(
    api_client, registration_payload, case_id, changes
):
    """Некорректные данные регистрации отклоняются."""

    payload = {
        **registration_payload,
        "phone": None,
        **changes,
    }

    response = api_client.post(
        "/register",
        json=payload,
    )

    assert response.status_code == 422, (
        f"{case_id}: {response.text}"
    )


@pytest.mark.parametrize(
    "case_id, changes, expected_status",
    [
        ("name_null", {"username": None}, 422),
        ("email_null", {"email": None}, 422),
        ("role_null", {"role": None}, 403),
        ("name_short", {"username": "abc"}, 422),
        ("email_bad", {"email": "invalid-email"}, 422),
        ("role_bad", {"role": "superadmin"}, 422),
    ],
)
def test_update_user_invalid_data(
    api_client, create_test_user,
    case_id, changes, expected_status
):
    """Некорректные изменения профиля отклоняются."""

    user, token = create_test_user(
        prefix=f"test_patch_{case_id}"
    )

    headers = auth_headers(token)

    response = api_client.patch(
        f"/users/{user['id']}",
        headers=headers,
        json=changes,
    )

    assert response.status_code == expected_status

    profile_response = api_client.get(
        "/users/self",
        headers=headers,
    )

    assert profile_response.status_code == 200

    profile = profile_response.json()

    assert profile["username"] == user["username"]
    assert profile["email"] == user["email"]
    assert profile["role"] == "employee"


def test_booking_invalid_date_format(
    api_client, admin_token, available_slot
):
    """Некорректный формат даты отклоняется."""

    room_id, slot_id = available_slot(
        admin_token, future_date(50)
    )

    response = api_client.post(
        "/bookings",
        headers=auth_headers(admin_token),
        json={
            "room_id": room_id,
            "time_window_id": slot_id,
            "date": "not-a-date",
        },
    )

    assert response.status_code == 422


def test_booking_past_date_is_rejected(
    api_client, admin_token, available_slot
):
    """Бронирование на прошедшую дату запрещено."""

    room_id, slot_id = available_slot(
        admin_token, future_date(50)
    )

    yesterday = (
        datetime.date.today()
        - datetime.timedelta(days=1)
    ).isoformat()

    response = api_client.post(
        "/bookings",
        headers=auth_headers(admin_token),
        json={
            "room_id": room_id,
            "time_window_id": slot_id,
            "date": yesterday,
        },
    )

    assert response.status_code == 400


def test_admin_cannot_set_role_to_null(
    api_client, admin_token
):
    """Нельзя присвоить администратору role=None."""

    headers = auth_headers(admin_token)

    profile_response = api_client.get(
        "/users/self",
        headers=headers,
    )

    assert profile_response.status_code == 200

    admin = profile_response.json()
    assert admin["role"] == "admin"

    response = api_client.patch(
        f"/users/{admin['id']}",
        headers=headers,
        json={"role": None},
    )

    assert response.status_code == 422

    profile_response = api_client.get(
        "/users/self",
        headers=headers,
    )

    assert profile_response.status_code == 200
    assert profile_response.json()["role"] == "admin"


@pytest.mark.parametrize(
    "missing_field",
    ["username", "password", "email"],
)
def test_registration_required_fields(
    api_client, registration_payload, missing_field
):
    """Проверяет обязательные поля регистрации."""

    payload = registration_payload.copy()
    del payload[missing_field]

    response = api_client.post(
        "/register",
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "changes",
    [
        {"username": "u" * 51},
        {"password": "x" * 129},
    ],
    ids=["username-too-long", "password-too-long"],
)
def test_registration_field_max_lengths(
    api_client, registration_payload, changes
):
    """Превышение максимальной длины отклоняется."""

    payload = {
        **registration_payload,
        **changes,
    }

    response = api_client.post(
        "/register",
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.parametrize("length", [4, 50])
def test_registration_valid_username_boundaries(
    api_client, registration_payload, length
):
    """Проверяет минимальную и максимальную длину username."""

    username = (
        "v" * (length - 4)
        + registration_payload["username"][-4:]
    )

    response = api_client.post(
        "/register",
        json={
            **registration_payload,
            "username": username,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["username"] == username
    assert response.json()["role"] == "employee"
    assert len(username) == length


@pytest.mark.parametrize(
    "endpoint",
    [
        "/users/not-an-id",
        "/rooms/not-an-id",
        "/bookings/not-an-id",
    ],
)
def test_invalid_path_identifiers(
    api_client, admin_token, endpoint
):
    """Некорректные идентификаторы URL отклоняются."""

    response = api_client.get(
        endpoint,
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "field",
    ["room_id", "time_window_id"],
)
def test_booking_invalid_id_types(
    api_client, admin_token, field
):
    """Идентификаторы бронирования должны быть числами."""

    payload = {
        "room_id": 1,
        "time_window_id": 1,
        "date": future_date(40),
    }

    payload[field] = "invalid-id"

    response = api_client.post(
        "/bookings",
        headers=auth_headers(admin_token),
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "case_id, password",
    [
        ("ascii", "x" * 73),
        ("unicode", "я" * 37),
    ],
)
def test_registration_password_byte_limit(
    api_client, registration_payload, case_id, password
):
    """Пароли длиннее 72 байт отклоняются."""

    payload = {
        **registration_payload,
        "password": password,
    }

    response = api_client.post(
        "/register",
        json=payload,
    )

    assert response.status_code == 422, (
        f"{case_id}: {response.text}"
    )
