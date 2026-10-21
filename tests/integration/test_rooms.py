"""Тесты: test_rooms."""


from tests.integration.helpers import auth_headers, future_date


def test_authorized_user_can_get_rooms(
    api_client, create_test_user
):
    """Авторизованный пользователь получает список комнат."""

    _, token = create_test_user()

    response = api_client.get(
        "/rooms",
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    rooms = response.json()["rooms"]

    assert isinstance(rooms, list)
    assert len(rooms) > 0

    room = rooms[0]

    assert "id" in room
    assert "room_name" in room
    assert "is_active" in room


def test_unauthorized_user_cannot_get_rooms(api_client):
    """Неавторизованный пользователь не получает комнаты."""

    response = api_client.get("/rooms")

    assert response.status_code in (401, 403)


def test_authorized_user_can_get_room_by_id(
    api_client, create_test_user
):
    """Авторизованный пользователь получает комнату по ID."""

    _, token = create_test_user()
    headers = auth_headers(token)

    rooms_response = api_client.get(
        "/rooms",
        headers=headers,
    )

    assert rooms_response.status_code == 200

    room = rooms_response.json()["rooms"][0]

    response = api_client.get(
        f"/rooms/{room['id']}",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["id"] == room["id"]
    assert response.json()["room_name"] == room["room_name"]


def test_authorized_user_can_get_available_rooms(
    api_client, create_test_user
):
    """Пользователь получает доступные комнаты и слоты."""

    _, token = create_test_user()

    response = api_client.get(
        f"/rooms/available/{future_date()}",
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    rooms = response.json()["rooms"]

    assert isinstance(rooms, list)
    assert len(rooms) > 0

    room = rooms[0]

    assert "id" in room
    assert "room_name" in room
    assert "available_time_windows" in room

    time_windows = room["available_time_windows"]

    assert isinstance(time_windows, list)
    assert len(time_windows) > 0

    slot = time_windows[0]

    assert "id" in slot
    assert "start_time" in slot
    assert "end_time" in slot


def test_unauthorized_user_cannot_get_available_rooms(
    api_client
):
    """Без авторизации нельзя получить доступные слоты."""

    response = api_client.get(
        f"/rooms/available/{future_date()}"
    )

    assert response.status_code in (401, 403)
