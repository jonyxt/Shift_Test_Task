"""Тесты: test_bookings."""


from tests.integration.helpers import auth_headers, future_date


def test_user_can_create_booking(
    create_test_user, create_test_booking
):
    """Пользователь может создать бронирование."""

    _, token = create_test_user()
    date = future_date(2)

    booking = create_test_booking(token, date)

    assert booking["date"] == date
    assert "room" in booking
    assert "time_window" in booking
    assert booking["is_active"] is True


def test_user_can_get_own_bookings(
    api_client, create_test_user, create_test_booking
):
    """Пользователь получает свои бронирования."""

    _, token = create_test_user()
    booking = create_test_booking(token, future_date(3))

    response = api_client.get(
        "/bookings",
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    booking_ids = [
        item["id"]
        for item in response.json()["bookings"]
    ]

    assert booking["id"] in booking_ids


def test_user_can_get_own_booking_by_id(
    api_client, create_test_user, create_test_booking
):
    """Пользователь получает своё бронирование по ID."""

    _, token = create_test_user()
    date = future_date(4)

    booking = create_test_booking(token, date)

    response = api_client.get(
        f"/bookings/{booking['id']}",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == booking["id"]
    assert response.json()["date"] == date


def test_user_can_cancel_own_booking(
    api_client, create_test_user, create_test_booking
):
    """Пользователь отменяет своё бронирование."""

    _, token = create_test_user()
    booking = create_test_booking(token, future_date(6))

    response = api_client.patch(
        f"/bookings/cancel/{booking['id']}",
        headers=auth_headers(token),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "Бронирование отменено"

    booking_response = api_client.get(
        f"/bookings/{booking['id']}",
        headers=auth_headers(token),
    )

    assert booking_response.status_code == 200
    assert booking_response.json()["is_active"] is False


def test_cancelled_booking_frees_slot(
    api_client, create_test_user, available_slot
):
    """После отмены слот снова можно забронировать."""

    _, token_1 = create_test_user()
    _, token_2 = create_test_user()

    date = future_date(9)
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

    booking_id = first_response.json()["id"]

    cancel_response = api_client.patch(
        f"/bookings/cancel/{booking_id}",
        headers=auth_headers(token_1),
    )

    assert cancel_response.status_code == 200

    second_response = api_client.post(
        "/bookings",
        headers=auth_headers(token_2),
        json=payload,
    )

    assert second_response.status_code == 200
    assert second_response.json()["is_active"] is True


def test_admin_can_get_all_bookings(
    api_client, admin_token,
    create_test_user, create_test_booking
):
    """Администратор получает все бронирования."""

    _, user_token = create_test_user()

    booking = create_test_booking(
        user_token, future_date(10)
    )

    response = api_client.get(
        "/bookings/all",
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200

    booking_ids = [
        item["id"]
        for item in response.json()["bookings"]
    ]

    assert booking["id"] in booking_ids


def test_admin_can_get_all_bookings_filtered_by_date(
    api_client, admin_token,
    create_test_user, create_test_booking
):
    """Администратор фильтрует бронирования по дате."""

    _, user_token = create_test_user()
    date = future_date(11)

    booking = create_test_booking(user_token, date)

    response = api_client.get(
        "/bookings/all",
        headers=auth_headers(admin_token),
        params={"date": date},
    )

    assert response.status_code == 200

    bookings = response.json()["bookings"]

    assert booking["id"] in [
        item["id"] for item in bookings
    ]
    assert all(item["date"] == date for item in bookings)


def test_admin_can_cancel_other_user_booking(
    api_client, admin_token,
    create_test_user, create_test_booking
):
    """Администратор отменяет чужое бронирование."""

    _, user_token = create_test_user()

    booking = create_test_booking(
        user_token, future_date(12)
    )

    response = api_client.patch(
        f"/bookings/cancel/{booking['id']}",
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200

    booking_response = api_client.get(
        f"/bookings/{booking['id']}",
        headers=auth_headers(admin_token),
    )

    assert booking_response.status_code == 200
    assert booking_response.json()["is_active"] is False


def test_slot_availability_after_booking_and_cancellation(
    api_client, create_test_user, available_slot
):
    """Доступность слота меняется при бронировании и отмене."""

    _, token = create_test_user()
    date = future_date(102)
    headers = auth_headers(token)

    room_id, slot_id = available_slot(token, date)

    def slot_is_available():
        response = api_client.get(
            f"/rooms/available/{date}",
            headers=headers,
        )

        assert response.status_code == 200

        return any(
            room["id"] == room_id
            and any(
                slot["id"] == slot_id
                for slot in room["available_time_windows"]
            )
            for room in response.json()["rooms"]
        )

    assert slot_is_available()

    response = api_client.post(
        "/bookings",
        headers=headers,
        json={
            "room_id": room_id,
            "time_window_id": slot_id,
            "date": date,
        },
    )

    assert response.status_code == 200

    booking_id = response.json()["id"]

    assert not slot_is_available()

    cancel_response = api_client.patch(
        f"/bookings/cancel/{booking_id}",
        headers=headers,
    )

    assert cancel_response.status_code == 200

    assert slot_is_available()
