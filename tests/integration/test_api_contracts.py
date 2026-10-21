"""Интеграционные тесты контрактов и безопасности HTTP API.

Входят в TASK-006. Тесты используют настоящие FastAPI и PostgreSQL,
поэтому располагаются в tests/integration/.
"""

import pytest

from tests.integration.helpers import auth_headers, future_date


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/users/self"),
        ("GET", "/users"),
        ("GET", "/users/1"),
        ("PATCH", "/users/1"),
        ("GET", "/rooms"),
        ("GET", "/rooms/1"),
        ("GET", "/rooms/available/{date}"),
        ("GET", "/bookings"),
        ("GET", "/bookings/all"),
        ("GET", "/bookings/1"),
        ("PATCH", "/bookings/cancel/1"),
        ("POST", "/bookings"),
    ],
)
def test_protected_routes_require_authorization(api_client, method, path):
    """Каждый защищённый маршрут отклоняет запрос без JWT."""

    path = path.format(date=future_date(5))
    kwargs = {}
    if (method, path) == ("PATCH", "/users/1"):
        kwargs["json"] = {"phone": "79990000000"}
    elif (method, path) == ("POST", "/bookings"):
        kwargs["json"] = {
            "room_id": 1,
            "time_window_id": 1,
            "date": future_date(5),
        }

    response = api_client.request(method, path, **kwargs)
    assert response.status_code == 401, f"{method} {path}: {response.text}"


@pytest.mark.parametrize(
    "path,params",
    [
        ("/bookings/all", {"date": "not-a-date"}),
        ("/bookings/all", {"date": "2027-02-30"}),
        ("/rooms/available/not-a-date", None),
        ("/rooms/available/2027-02-30", None),
    ],
)
def test_invalid_date_query_is_rejected(api_client, admin_token, path, params):
    """Неправильные даты в URL или query-параметрах возвращают 422."""

    response = api_client.get(
        path,
        headers=auth_headers(admin_token),
        params=params,
    )
    assert response.status_code == 422, response.text


def test_own_bookings_do_not_include_other_users_bookings(
    api_client, create_test_user, create_test_booking,
):
    """Список /bookings содержит только бронирования текущего пользователя."""

    user_1, token_1 = create_test_user()
    user_2, token_2 = create_test_user()
    booking_1 = create_test_booking(token_1, future_date(131))
    booking_2 = create_test_booking(token_2, future_date(132))

    response_1 = api_client.get("/bookings", headers=auth_headers(token_1))
    response_2 = api_client.get("/bookings", headers=auth_headers(token_2))

    assert response_1.status_code == 200
    assert response_2.status_code == 200

    bookings_1 = response_1.json()["bookings"]
    bookings_2 = response_2.json()["bookings"]

    assert {item["id"] for item in bookings_1} == {booking_1["id"]}
    assert {item["id"] for item in bookings_2} == {booking_2["id"]}
    assert all(item["owner"]["id"] == user_1["id"] for item in bookings_1)
    assert all(item["owner"]["id"] == user_2["id"] for item in bookings_2)


@pytest.mark.parametrize("cancel_as_admin", [False, True], ids=["owner", "admin"])
def test_booking_cancellation_records_actor(
    api_client, create_test_user, create_test_booking, admin_token,
    cancel_as_admin,
):
    """После отмены сохраняются cancelled_at и cancelled_by."""

    owner, owner_token = create_test_user()
    booking = create_test_booking(
        owner_token, future_date(140 if cancel_as_admin else 141)
    )
    assert booking["is_active"] is True
    assert booking["cancelled_at"] is None
    assert booking["cancelled_by"] is None

    if cancel_as_admin:
        actor_token = admin_token
        actor_response = api_client.get(
            "/users/self", headers=auth_headers(admin_token)
        )
        assert actor_response.status_code == 200
        actor_id = actor_response.json()["id"]
    else:
        actor_token = owner_token
        actor_id = owner["id"]

    cancel_response = api_client.patch(
        f"/bookings/cancel/{booking['id']}",
        headers=auth_headers(actor_token),
    )
    assert cancel_response.status_code == 200

    details_response = api_client.get(
        f"/bookings/{booking['id']}",
        headers=auth_headers(owner_token),
    )
    assert details_response.status_code == 200
    data = details_response.json()

    assert data["is_active"] is False
    assert data["cancelled_at"] is not None
    assert data["cancelled_by"]["id"] == actor_id
    assert data["created_at"] == booking["created_at"]


def test_user_can_clear_optional_phone(api_client, create_test_user):
    """Необязательное поле phone можно сбросить в null."""

    user, token = create_test_user()
    headers = auth_headers(token)
    path = f"/users/{user['id']}"
    phone = f"79{user['id']:09d}"

    set_response = api_client.patch(path, headers=headers, json={"phone": phone})
    assert set_response.status_code == 200
    assert set_response.json()["phone"] == phone

    clear_response = api_client.patch(path, headers=headers, json={"phone": None})
    assert clear_response.status_code == 200
    assert clear_response.json()["phone"] is None

    profile_response = api_client.get("/users/self", headers=headers)
    assert profile_response.status_code == 200
    assert profile_response.json()["phone"] is None


def test_role_changes_take_effect_for_existing_token(
    api_client, admin_token, create_test_user,
):
    """Права берутся из БД, а не фиксируются в JWT при его выдаче."""

    user, token = create_test_user()
    user_headers = auth_headers(token)
    admin_headers = auth_headers(admin_token)
    path = f"/users/{user['id']}"

    initial_response = api_client.get("/users", headers=user_headers)
    assert initial_response.status_code == 403

    promote_response = api_client.patch(
        path, headers=admin_headers, json={"role": "admin"}
    )
    assert promote_response.status_code == 200

    try:
        promoted_access = api_client.get("/users", headers=user_headers)
        assert promoted_access.status_code == 200
    finally:
        restore_response = api_client.patch(
            path, headers=admin_headers, json={"role": "employee"}
        )
        assert restore_response.status_code == 200

    revoked_access = api_client.get("/users", headers=user_headers)
    assert revoked_access.status_code == 403


def test_public_api_responses_do_not_leak_credentials(
    api_client, admin_token, create_test_user, create_test_booking,
):
    """Публичные ответы не содержат пароль, его хеш или токен."""

    user, token = create_test_user()
    booking = create_test_booking(token, future_date(155))

    responses = [
        api_client.get("/users/self", headers=auth_headers(token)),
        api_client.get("/users", headers=auth_headers(admin_token)),
        api_client.get(
            f"/users/{user['id']}", headers=auth_headers(admin_token)
        ),
        api_client.get(
            f"/bookings/{booking['id']}", headers=auth_headers(token)
        ),
    ]

    for response in responses:
        assert response.status_code == 200
        body = response.text.lower()
        for forbidden in (
            "hashed_password", "password_hash", "secret_key", "access_token",
            "password123", token.lower(),
        ):
            assert forbidden not in body
