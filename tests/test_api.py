"""Интеграционные тесты HTTP API.

Тесты обращаются к запущенному приложению через реальные HTTP-запросы
и проверяют основные пользовательские сценарии: регистрацию, авторизацию,
работу с пользователями, комнатами и бронированиями.
"""
import os
import httpx
import datetime

BASE_URL = os.getenv('BASE_URL', 'http://app:8000')

def register_user(username: str, email: str, password: str = 'password123') -> httpx.Response:
    """Регистрирует пользователя через API и возвращает HTTP-ответ."""

    return httpx.post(
        f"{BASE_URL}/register",
        json={
            'username': username,
            'email': email,
            'password': password,
            'phone': None
        },
    )

def login_user(username: str, password: str = 'password123') -> str:
    """Авторизует пользователя через API и возвращает JWT-токен."""

    response = httpx.post(
        f"{BASE_URL}/login",
        json={
            'username': username,
            'password': password
        },
    )
    assert response.status_code == 200
    return response.json()['access_token']

def auth_headers(token: str) -> dict:
    """Формирует заголовок Authorization для запросов с JWT-токеном."""

    return {
        'Authorization': f"Bearer {token}"
    }

def create_user_and_token(username: str, email: str, password: str = 'password123'):
    """Создает пользователя, авторизует его и возвращает данные пользователя вместе с токеном."""

    register_response = register_user(
        username=username,
        email=email,
        password=password
    )
    assert register_response.status_code == 200
    token = login_user(username=username, password=password)
    return register_response.json(), token

def future_date(days: int = 1) -> str:
    """Возвращает дату на указанное количество дней позже текущей даты."""

    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()

def get_first_available_slot(token: str, date: str):
    """Получает первый доступный слот для указанной даты.

    Функция используется в тестах, где нужно создать бронирование без привязки
    к конкретной комнате или временному слоту.
    """

    response = httpx.get(
        f"{BASE_URL}/rooms/available/{date}",
        headers=auth_headers(token)
    )
    assert response.status_code == 200
    rooms = response.json()['rooms']
    assert len(rooms) > 0
    room = rooms[0]
    time_windows = room['available_time_windows']
    assert len(time_windows) > 0
    return room['id'], time_windows[0]['id']

def create_booking(token: str, date: str) -> dict:
    """Создает бронирование через API и возвращает данные созданного бронирования."""

    room_id, time_window_id = get_first_available_slot(token, date)
    response = httpx.post(
        f"{BASE_URL}/bookings",
        headers=auth_headers(token),
        json={
            'room_id': room_id,
            'time_window_id': time_window_id,
            'date': date
        }
    )
    assert response.status_code == 200
    return response.json()

def test_openapi_is_available():
    """Проверяет, что OpenAPI-схема доступна после запуска приложения."""

    response = httpx.get(f"{BASE_URL}/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert 'paths' in data

def test_first_registered_user_is_admin():
    """Проверяет, что первый зарегистрированный пользователь получает роль администратора."""

    response = register_user(
        username='test_first_admin',
        email='test_first_admin@example.com'
    )
    assert response.status_code == 200
    data = response.json()
    assert data['role'] == 'admin'

def test_register_user():
    """Проверяет успешную регистрацию пользователя."""

    response = register_user(
        username='test_register_user',
        email='test_register_user@example.com'
    )
    assert response.status_code == 200
    data = response.json()
    assert data['username'] == 'test_register_user'
    assert data['email'] == 'test_register_user@example.com'
    assert 'id' in data
    assert 'hashed_password' not in data

def test_login_user():
    """Проверяет успешную авторизацию пользователя."""

    username = 'test_login_user'
    password = 'password123'
    register_user(
        username=username,
        email='test_login_user@example.com',
        password=password
    )
    response = httpx.post(
        f"{BASE_URL}/login",
        json={
            'username': username,
            'password': password
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data['token_type'] == 'bearer'
    assert isinstance(data['access_token'], str)
    assert len(data['access_token']) > 0

def test_get_current_user():
    """Проверяет получение профиля текущего пользователя."""

    user, token = create_user_and_token(
        username='test_self_user',
        email='test_self_user@example.com'
    )
    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(token)
    )
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == user['id']
    assert data['username'] == user['username']
    assert data['email'] == user['email']

def test_admin_can_get_users():
    """Проверяет, что администратор может получить список пользователей."""

    admin_token = login_user('test_first_admin')
    response = httpx.get(
        f"{BASE_URL}/users",
        headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    data = response.json()
    assert 'users' in data
    assert isinstance(data['users'], list)
    assert len(data['users']) > 0

def test_admin_can_get_user_by_id():
    """Проверяет, что администратор может получить пользователя по id."""

    admin_token = login_user('test_first_admin')
    user, _token = create_user_and_token(
        username='test_get_user_by_id',
        email='test_get_user_by_id@example.com'
    )
    response = httpx.get(
        f"{BASE_URL}/users/{user['id']}",
        headers=auth_headers(admin_token)
    )
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == user['id']
    assert data['username'] == user['username']
    assert data['email'] == user['email']

def test_user_can_update_self():
    """Проверяет, что пользователь может обновить свой профиль."""

    user, token = create_user_and_token(
        username='test_update_self',
        email='test_update_self@example.com'
    )
    response = httpx.patch(
        f"{BASE_URL}/users/{user['id']}",
        headers=auth_headers(token),
        json={'phone': '79999999999'},
    )
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == user['id']
    assert data['phone'] == '79999999999'

def test_employee_cannot_update_other_user():
    """Проверяет, что сотрудник не может обновить профиль другого пользователя."""

    _user_1, user_1_token = create_user_and_token(
        username='test_update_other_1',
        email='test_update_other_1@example.com'
    )
    user_2, _user_2_token = create_user_and_token(
        username='test_update_other_2',
        email='test_update_other_2@example.com'
    )
    response = httpx.patch(
        f"{BASE_URL}/users/{user_2['id']}",
        headers=auth_headers(user_1_token),
        json={'phone': '78888888888'},
    )
    assert response.status_code == 403

def test_employee_cannot_get_users():
    """Проверяет, что сотрудник не может получить список всех пользователей."""

    _user, token = create_user_and_token(
        username='test_employee_cannot_get_users',
        email='test_employee_cannot_get_users@example.com'
    )
    response = httpx.get(
        f"{BASE_URL}/users",
        headers=auth_headers(token)
    )
    assert response.status_code == 403

def test_authorized_user_can_get_rooms():
    """Проверяет, что авторизованный пользователь может получить список комнат."""

    _user, token = create_user_and_token(
        username='test_get_rooms',
        email='test_get_rooms@example.com'
    )
    response = httpx.get(
        f"{BASE_URL}/rooms",
        headers=auth_headers(token)
    )
    assert response.status_code == 200
    data = response.json()
    assert 'rooms' in data
    assert isinstance(data['rooms'], list)
    assert len(data['rooms']) > 0
    room = data['rooms'][0]
    assert 'id' in room
    assert 'room_name' in room
    assert 'is_active' in room

def test_unauthorized_user_cannot_get_rooms():
    """Проверяет, что без токена нельзя получить список комнат."""

    response = httpx.get(f"{BASE_URL}/rooms")
    assert response.status_code in (401, 403)

def test_authorized_user_can_get_room_by_id():
    """Проверяет получение комнаты по id."""

    _user, token = create_user_and_token(
        username='test_get_room_by_id',
        email='test_get_room_by_id@example.com'
    )
    rooms_response = httpx.get(
        f"{BASE_URL}/rooms",
        headers=auth_headers(token)
    )
    assert rooms_response.status_code == 200
    room = rooms_response.json()['rooms'][0]
    response = httpx.get(
        f"{BASE_URL}/rooms/{room['id']}",
        headers=auth_headers(token)
    )
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == room['id']
    assert data['room_name'] == room['room_name']

def test_authorized_user_can_get_available_rooms():
    """Проверяет получение доступных комнат и слотов на будущую дату."""

    _user, token = create_user_and_token(
        username='test_get_available_rooms',
        email='test_get_available_rooms@example.com'
    )
    response = httpx.get(
        f"{BASE_URL}/rooms/available/{future_date()}",
        headers=auth_headers(token)
    )
    assert response.status_code == 200
    data = response.json()
    assert 'rooms' in data
    assert isinstance(data['rooms'], list)
    assert len(data['rooms']) > 0
    room = data['rooms'][0]
    assert 'id' in room
    assert 'room_name' in room
    assert 'available_time_windows' in room
    assert isinstance(room['available_time_windows'], list)
    assert len(room['available_time_windows']) > 0
    time_window = room['available_time_windows'][0]
    assert 'id' in time_window
    assert 'start_time' in time_window
    assert 'end_time' in time_window

def test_unauthorized_user_cannot_get_available_rooms():
    """Проверяет, что без токена нельзя получить доступные комнаты и слоты."""

    response = httpx.get(f"{BASE_URL}/rooms/available/{future_date()}")
    assert response.status_code in (401, 403)

def test_user_can_create_booking():
    """Проверяет создание бронирования."""

    _user, token = create_user_and_token(
        username='test_create_booking',
        email='test_create_booking@example.com'
    )
    date = future_date(2)
    booking = create_booking(token, date)
    assert booking['date'] == date
    assert 'room' in booking
    assert 'time_window' in booking
    assert booking['is_active'] is True

def test_user_can_get_own_bookings():
    """Проверяет получение всех бронирований текущего пользователя."""

    _user, token = create_user_and_token(
        username='test_get_own_bookings',
        email='test_get_own_bookings@example.com'
    )
    booking = create_booking(token, future_date(3))
    response = httpx.get(
        f"{BASE_URL}/bookings",
        headers=auth_headers(token)
    )
    assert response.status_code == 200
    data = response.json()
    booking_ids = [item['id'] for item in data['bookings']]
    assert booking['id'] in booking_ids

def test_user_can_get_own_booking_by_id():
    """Проверяет получение своего бронирования по id."""

    _user, token = create_user_and_token(
        username='test_get_own_booking_by_id',
        email='test_get_own_booking_by_id@example.com'
    )
    date = future_date(4)
    booking = create_booking(token, date)
    response = httpx.get(
        f"{BASE_URL}/bookings/{booking['id']}",
        headers=auth_headers(token)
    )
    assert response.status_code == 200
    data = response.json()
    assert data['id'] == booking['id']
    assert data['date'] == date

def test_employee_cannot_get_other_user_booking_by_id():
    """Проверяет, что сотрудник не может получить чужое бронирование по id."""
    _user_1, user_1_token = create_user_and_token(
        username='test_other_booking_1',
        email='test_other_booking_1@example.com'
    )
    _user_2, user_2_token = create_user_and_token(
        username='test_other_booking_2',
        email='test_other_booking_2@example.com'
    )
    booking = create_booking(user_1_token, future_date(5))
    response = httpx.get(
        f"{BASE_URL}/bookings/{booking['id']}",
        headers=auth_headers(user_2_token)
    )
    assert response.status_code == 403

def test_user_can_cancel_own_booking():
    """Проверяет отмену своего бронирования."""

    _user, token = create_user_and_token(
        username="test_cancel_own_booking",
        email="test_cancel_own_booking@example.com",
    )
    booking = create_booking(token, future_date(6))
    response = httpx.patch(
        f"{BASE_URL}/bookings/cancel/{booking['id']}",
        headers=auth_headers(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Бронирование отменено"
    booking_response = httpx.get(
        f"{BASE_URL}/bookings/{booking['id']}",
        headers=auth_headers(token),
    )
    assert booking_response.status_code == 200
    booking_data = booking_response.json()
    assert booking_data["is_active"] is False

def test_employee_cannot_cancel_other_user_booking():
    """Проверяет, что сотрудник не может отменить чужое бронирование."""

    _user_1, user_1_token = create_user_and_token(
        username='test_cancel_other_booking_1',
        email='test_cancel_other_booking_1@example.com'
    )
    _user_2, user_2_token = create_user_and_token(
        username='test_cancel_other_booking_2',
        email='test_cancel_other_booking_2@example.com'
    )
    booking = create_booking(user_1_token, future_date(7))
    response = httpx.patch(
        f"{BASE_URL}/bookings/cancel/{booking['id']}",
        headers=auth_headers(user_2_token),
    )
    assert response.status_code == 403
    booking_response = httpx.get(
        f"{BASE_URL}/bookings/{booking['id']}",
        headers=auth_headers(user_1_token),
    )
    assert booking_response.status_code == 200
    assert booking_response.json()["is_active"] is True

def test_user_cannot_book_already_booked_slot():
    """Проверяет запрет повторного активного бронирования одного и того же слота."""

    _user_1, user_1_token = create_user_and_token(
        username="test_double_booking_1",
        email="test_double_booking_1@example.com",
    )
    _user_2, user_2_token = create_user_and_token(
        username="test_double_booking_2",
        email="test_double_booking_2@example.com",
    )
    date = future_date(8)
    room_id, time_window_id = get_first_available_slot(user_1_token, date)
    first_response = httpx.post(
        f"{BASE_URL}/bookings",
        headers=auth_headers(user_1_token),
        json={
            "room_id": room_id,
            "time_window_id": time_window_id,
            "date": date,
        },
    )
    assert first_response.status_code == 200
    second_response = httpx.post(
        f"{BASE_URL}/bookings",
        headers=auth_headers(user_2_token),
        json={
            "room_id": room_id,
            "time_window_id": time_window_id,
            "date": date,
        },
    )
    assert second_response.status_code == 409

def test_cancelled_booking_frees_slot():
    """Проверяет, что после отмены бронирования слот снова становится доступным."""

    _user_1, user_1_token = create_user_and_token(
        username="test_cancel_frees_slot_1",
        email="test_cancel_frees_slot_1@example.com",
    )
    _user_2, user_2_token = create_user_and_token(
        username="test_cancel_frees_slot_2",
        email="test_cancel_frees_slot_2@example.com",
    )
    date = future_date(9)
    room_id, time_window_id = get_first_available_slot(user_1_token, date)
    first_response = httpx.post(
        f"{BASE_URL}/bookings",
        headers=auth_headers(user_1_token),
        json={
            "room_id": room_id,
            "time_window_id": time_window_id,
            "date": date,
        },
    )
    assert first_response.status_code == 200
    booking = first_response.json()
    cancel_response = httpx.patch(
        f"{BASE_URL}/bookings/cancel/{booking['id']}",
        headers=auth_headers(user_1_token),
    )
    assert cancel_response.status_code == 200
    second_response = httpx.post(
        f"{BASE_URL}/bookings",
        headers=auth_headers(user_2_token),
        json={
            "room_id": room_id,
            "time_window_id": time_window_id,
            "date": date,
        },
    )
    assert second_response.status_code == 200
    assert second_response.json()["is_active"] is True

def test_admin_can_get_all_bookings():
    """Проверяет, что администратор может получить все бронирования."""

    admin_token = login_user("test_first_admin")
    _user, user_token = create_user_and_token(
        username="test_admin_get_all_bookings_user",
        email="test_admin_get_all_bookings_user@example.com",
    )
    booking = create_booking(user_token, future_date(10))
    response = httpx.get(
        f"{BASE_URL}/bookings/all",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    data = response.json()
    assert "bookings" in data
    booking_ids = [item["id"] for item in data["bookings"]]
    assert booking["id"] in booking_ids

def test_admin_can_get_all_bookings_filtered_by_date():
    """Проверяет фильтрацию всех бронирований по дате для администратора."""

    admin_token = login_user("test_first_admin")
    _user, user_token = create_user_and_token(
        username="test_admin_get_bookings_by_date_user",
        email="test_admin_get_bookings_by_date_user@example.com",
    )
    date = future_date(11)
    booking = create_booking(user_token, date)
    response = httpx.get(
        f"{BASE_URL}/bookings/all",
        headers=auth_headers(admin_token),
        params={
            "date": date,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "bookings" in data
    booking_ids = [item["id"] for item in data["bookings"]]
    assert booking["id"] in booking_ids
    assert all(item["date"] == date for item in data["bookings"])

def test_employee_cannot_get_all_bookings():
    """Проверяет, что сотрудник не может получить список всех бронирований."""

    _user, token = create_user_and_token(
        username="test_employee_get_all_bookings",
        email="test_employee_get_all_bookings@example.com",
    )
    response = httpx.get(
        f"{BASE_URL}/bookings/all",
        headers=auth_headers(token),
    )
    assert response.status_code == 403

def test_admin_can_cancel_other_user_booking():
    """Проверяет, что администратор может отменить бронирование другого пользователя."""

    admin_token = login_user("test_first_admin")
    _user, user_token = create_user_and_token(
        username="test_admin_cancel_other_booking_user",
        email="test_admin_cancel_other_booking_user@example.com",
    )
    booking = create_booking(user_token, future_date(12))
    response = httpx.patch(
        f"{BASE_URL}/bookings/cancel/{booking['id']}",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200
    booking_response = httpx.get(
        f"{BASE_URL}/bookings/{booking['id']}",
        headers=auth_headers(admin_token),
    )
    assert booking_response.status_code == 200
    assert booking_response.json()["is_active"] is False