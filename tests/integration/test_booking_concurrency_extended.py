from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest

from tests.integration.helpers import BASE_URL, auth_headers, future_date


def run_together(operations):
    """Стартует HTTP-операции из разных потоков одновременно."""
    barrier = Barrier(len(operations))

    def worker(operation):
        barrier.wait(timeout=15)
        return operation()

    with ThreadPoolExecutor(max_workers=len(operations)) as pool:
        return list(pool.map(worker, operations))


def book(token, payload):
    # Каждый вызов создаёт свой HTTP-клиент; между потоками нет общего состояния.
    return httpx.post(
        f"{BASE_URL}/bookings",
        headers=auth_headers(token),
        json=payload,
        timeout=25,
    )


def cancel(token, booking_id):
    return httpx.patch(
        f"{BASE_URL}/bookings/cancel/{booking_id}",
        headers=auth_headers(token),
        timeout=25,
    )


def active_for_slot(api_client, admin_token, date, room_id, slot_id):
    response = api_client.get(
        "/bookings/all",
        headers=auth_headers(admin_token),
        params={"date": date},
    )
    assert response.status_code == 200, response.text

    return [
        item for item in response.json()["bookings"]
        if item["room"]["id"] == room_id
        and item["time_window"]["id"] == slot_id
        and item["is_active"]
    ]


@pytest.mark.parametrize("contenders", [3, 5], ids=["three", "five"])
def test_many_users_compete_for_one_slot(
    api_client, create_test_user, available_slot, admin_token, contenders
):
    """Среди 3/5 одновременных заявок успешна только одна."""
    tokens = [create_test_user()[1] for _ in range(contenders)]
    date = future_date(210 + contenders)
    room_id, slot_id = available_slot(tokens[0], date)
    payload = {"room_id": room_id, "time_window_id": slot_id, "date": date}

    responses = run_together([
        lambda token=token: book(token, payload)
        for token in tokens
    ])

    assert sorted(response.status_code for response in responses) == (
        [200] + [409] * (contenders - 1)
    ), [(response.status_code, response.text) for response in responses]

    active = active_for_slot(api_client, admin_token, date, room_id, slot_id)
    assert len(active) == 1
    winner_booking_id = next(
        response.json()["id"]
        for response in responses
        if response.status_code == 200
    )
    assert active[0]["id"] == winner_booking_id


def test_one_user_cannot_double_book_same_slot_concurrently(
    api_client, create_test_user, available_slot, admin_token
):
    """Даже один пользователь не может создать две активные брони одного слота."""
    _, token = create_test_user()
    date = future_date(216)
    room_id, slot_id = available_slot(token, date)
    payload = {"room_id": room_id, "time_window_id": slot_id, "date": date}

    responses = run_together([
        lambda: book(token, payload),
        lambda: book(token, payload),
    ])

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert len(active_for_slot(api_client, admin_token, date, room_id, slot_id)) == 1


def test_different_slots_can_be_booked_concurrently(
    api_client, create_test_user, admin_token
):
    """Брони разных слотов одной комнаты не блокируют друг друга."""
    token_1 = create_test_user()[1]
    token_2 = create_test_user()[1]
    date = future_date(217)

    response = api_client.get(
        f"/rooms/available/{date}",
        headers=auth_headers(token_1),
    )
    assert response.status_code == 200, response.text
    rooms = response.json()["rooms"]
    room = next(
        (item for item in rooms if len(item["available_time_windows"]) >= 2),
        None,
    )
    assert room is not None, "Нужна комната с двумя свободными слотами"
    room_id = room["id"]
    slot_1, slot_2 = [
        window["id"] for window in room["available_time_windows"][:2]
    ]

    responses = run_together([
        lambda: book(token_1, {
            "room_id": room_id, "time_window_id": slot_1, "date": date
        }),
        lambda: book(token_2, {
            "room_id": room_id, "time_window_id": slot_2, "date": date
        }),
    ])

    assert [response.status_code for response in responses] == [200, 200]
    assert len(active_for_slot(api_client, admin_token, date, room_id, slot_1)) == 1
    assert len(active_for_slot(api_client, admin_token, date, room_id, slot_2)) == 1


def test_simultaneous_cancel_same_booking_is_not_double_success(
    api_client, create_test_user, create_test_booking, admin_token
):
    """Два запроса отмены одной брони: 200 и 400, но не два 200."""
    owner, owner_token = create_test_user()
    booking = create_test_booking(owner_token, future_date(218))

    responses = run_together([
        lambda: cancel(owner_token, booking["id"]),
        lambda: cancel(admin_token, booking["id"]),
    ])

    assert sorted(response.status_code for response in responses) == [200, 400], [
        (response.status_code, response.text) for response in responses
    ]

    response = api_client.get(
        f"/bookings/{booking['id']}",
        headers=auth_headers(owner_token),
    )
    assert response.status_code == 200
    result = response.json()
    assert result["is_active"] is False
    assert result["cancelled_at"] is not None

    admin_response = api_client.get(
        "/users/self", headers=auth_headers(admin_token)
    )
    assert admin_response.status_code == 200
    assert result["cancelled_by"]["id"] in {
        owner["id"], admin_response.json()["id"]
    }
    assert cancel(owner_token, booking["id"]).status_code == 400


def test_different_bookings_can_be_cancelled_concurrently(
    api_client, create_test_user, create_test_booking
):
    """Отмена независимых броней не создаёт ложных конфликтов."""
    token_1 = create_test_user()[1]
    token_2 = create_test_user()[1]
    date = future_date(219)
    booking_1 = create_test_booking(token_1, date)
    booking_2 = create_test_booking(token_2, date)
    assert booking_1["id"] != booking_2["id"]

    responses = run_together([
        lambda: cancel(token_1, booking_1["id"]),
        lambda: cancel(token_2, booking_2["id"]),
    ])

    assert [response.status_code for response in responses] == [200, 200]
    for token, booking in [(token_1, booking_1), (token_2, booking_2)]:
        response = api_client.get(
            f"/bookings/{booking['id']}", headers=auth_headers(token)
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False


def test_cancel_and_competing_rebooking_preserve_slot_invariant(
    api_client, create_test_user, admin_token, available_slot
):
    """При гонке отмены и новой брони активных записей не больше одной."""
    owner_token = create_test_user()[1]
    other_token = create_test_user()[1]
    date = future_date(220)
    room_id, slot_id = available_slot(owner_token, date)
    payload = {"room_id": room_id, "time_window_id": slot_id, "date": date}

    initial = api_client.post(
        "/bookings", headers=auth_headers(owner_token), json=payload
    )
    assert initial.status_code == 200, initial.text
    first_booking_id = initial.json()["id"]

    cancel_response, book_response = run_together([
        lambda: cancel(owner_token, first_booking_id),
        lambda: book(other_token, payload),
    ])

    assert cancel_response.status_code == 200, cancel_response.text
    assert book_response.status_code in (200, 409), book_response.text

    active = active_for_slot(api_client, admin_token, date, room_id, slot_id)
    assert len(active) == (1 if book_response.status_code == 200 else 0)
    if book_response.status_code == 200:
        assert active[0]["id"] == book_response.json()["id"]
    assert all(item["id"] != first_booking_id for item in active)


def test_same_slot_can_be_booked_concurrently_on_different_dates(
    api_client, create_test_user, available_slot, admin_token
):
    """Уникальность слота учитывает дату бронирования."""
    token_1 = create_test_user()[1]
    token_2 = create_test_user()[1]
    date_1, date_2 = future_date(221), future_date(222)
    room_id, slot_id = available_slot(token_1, date_1)

    responses = run_together([
        lambda: book(token_1, {
            "room_id": room_id, "time_window_id": slot_id, "date": date_1
        }),
        lambda: book(token_2, {
            "room_id": room_id, "time_window_id": slot_id, "date": date_2
        }),
    ])

    assert [response.status_code for response in responses] == [200, 200]
    assert len(active_for_slot(api_client, admin_token, date_1, room_id, slot_id)) == 1
    assert len(active_for_slot(api_client, admin_token, date_2, room_id, slot_id)) == 1
