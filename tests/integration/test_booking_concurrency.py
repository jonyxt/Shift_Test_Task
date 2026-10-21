import httpx
from concurrent.futures import ThreadPoolExecutor
from tests.integration.helpers import BASE_URL, auth_headers, future_date


def test_concurrent_booking_only_one_succeeds(
    api_client, create_test_user,
    available_slot, admin_token
):
    """Одновременно только один пользователь занимает слот."""

    _, token_1 = create_test_user()
    _, token_2 = create_test_user()

    date = future_date(103)

    room_id, slot_id = available_slot(
        token_1, date
    )

    payload = {
        "room_id": room_id,
        "time_window_id": slot_id,
        "date": date,
    }

    def try_book(token):
        # Отдельные HTTP-запросы из разных потоков.
        return httpx.post(
            f"{BASE_URL}/bookings",
            headers=auth_headers(token),
            json=payload,
            timeout=20,
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(try_book, [token_1, token_2])
        )

    statuses = sorted(
        response.status_code for response in responses
    )

    assert statuses == [200, 409]

    response = api_client.get(
        "/bookings/all",
        headers=auth_headers(admin_token),
        params={"date": date},
    )

    assert response.status_code == 200

    active_bookings = [
        booking
        for booking in response.json()["bookings"]
        if booking["room"]["id"] == room_id
        and booking["time_window"]["id"] == slot_id
        and booking["is_active"]
    ]

    assert len(active_bookings) == 1
