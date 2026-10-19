"""Интеграционные тесты HTTP API.

Тесты обращаются к запущенному приложению через реальные HTTP-запросы
и проверяют основные пользовательские сценарии: регистрацию, авторизацию,
работу с пользователями, комнатами и бронированиями.
"""
import os
import httpx
import datetime
import jwt
import pytest
import asyncio

from sqlalchemy import delete
from app import models
from app.config import config
from app.database import AsyncSessionLocal, engine
from app import auth
from concurrent.futures import ThreadPoolExecutor


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
    assert register_response.status_code == 200, register_response.text
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

def test_register_cannot_choose_admin_role():
    response = httpx.post(
        f"{BASE_URL}/register",
        json={
            "username": "test_role_escalation",
            "email": "role_escalation@example.com",
            "password": "password123",
            "role": "admin",
        },
    )

    assert response.status_code == 200
    assert response.json()["role"] == "employee"

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
    assert data['role'] == 'employee'
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


def test_employee_cannot_assign_admin_role_to_self():
    """Сотрудник не может назначить себе роль администратора."""

    user, token = create_user_and_token(
        username="test_forbid_self_admin",
        email="test_role_escalation@example.com"
    )

    assert user["role"] == "employee"

    response = httpx.patch(
        f"{BASE_URL}/users/{user['id']}",
        headers=auth_headers(token),
        json={"role": "admin"}
    )

    assert response.status_code == 403

    profile_response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(token)
    )

    assert profile_response.status_code == 200
    assert profile_response.json()["role"] == "employee"


def test_employee_cannot_get_other_user_by_id():
    """Сотрудник не может получить чужой профиль по ID."""

    user_1, token_1 = create_user_and_token(
        username="test_forbidden_read_1",
        email="test_forbidden_read_1@example.com"
    )

    user_2, _token_2 = create_user_and_token(
        username="test_forbidden_read_2",
        email="test_forbidden_read_2@example.com"
    )

    assert user_1["id"] != user_2["id"]

    response = httpx.get(
        f"{BASE_URL}/users/{user_2['id']}",
        headers=auth_headers(token_1)
    )

    assert response.status_code == 403


def test_admin_can_change_user_role():
    """Администратор может назначать и отзывать роль admin."""

    admin_token = login_user("test_first_admin")

    user, _token = create_user_and_token(
        username="test_admin_role_change",
        email="test_admin_role_change@example.com"
    )

    assert user["role"] == "employee"

    # Повышаем сотрудника до администратора
    response = httpx.patch(
        f"{BASE_URL}/users/{user['id']}",
        headers=auth_headers(admin_token),
        json={"role": "admin"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    # Проверяем сохранённую роль
    response = httpx.get(
        f"{BASE_URL}/users/{user['id']}",
        headers=auth_headers(admin_token)
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    # Возвращаем обычную роль
    response = httpx.patch(
        f"{BASE_URL}/users/{user['id']}",
        headers=auth_headers(admin_token),
        json={"role": "employee"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "employee"


def test_cannot_demote_last_admin():
    """Нельзя снять роль у последнего администратора."""

    admin_token = login_user("test_first_admin")

    # Получаем профиль администратора
    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(admin_token)
    )

    assert response.status_code == 200
    admin = response.json()
    assert admin["role"] == "admin"

    # Проверяем, что администратор единственный
    users_response = httpx.get(
        f"{BASE_URL}/users",
        headers=auth_headers(admin_token)
    )

    assert users_response.status_code == 200

    admins = [
        user for user in users_response.json()["users"]
        if user["role"] == "admin"
    ]

    assert len(admins) == 1
    assert admins[0]["id"] == admin["id"]

    # Пытаемся снять роль администратора
    response = httpx.patch(
        f"{BASE_URL}/users/{admin['id']}",
        headers=auth_headers(admin_token),
        json={"role": "employee"}
    )

    assert response.status_code == 400

    # Проверяем, что роль не изменилась
    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(admin_token)
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_tampered_jwt_signature_is_rejected():
    """Сервер отклоняет JWT с изменённой подписью."""

    token = login_user("test_first_admin")

    # Проверяем, что оригинальный токен работает
    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(token)
    )
    assert response.status_code == 200

    # Разделяем JWT на три части
    header, payload, signature = token.split(".")

    # Изменяем первый символ подписи
    changed_char = "A" if signature[0] != "A" else "B"

    fake_token = (
        f"{header}.{payload}."
        f"{changed_char}{signature[1:]}"
    )

    # Пробуем авторизоваться с поддельным токеном
    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(fake_token)
    )

    assert response.status_code == 401


def test_expired_jwt_is_rejected():
    """Сервер отклоняет JWT с истёкшим сроком действия."""

    token = login_user("test_first_admin")

    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(token)
    )

    assert response.status_code == 200
    user_id = response.json()["id"]

    # Создаём действительный подписанный JWT
    valid_token = jwt.encode(
        {
            "sub": str(user_id),
            "exp": datetime.datetime.now(
                datetime.timezone.utc
            ) + datetime.timedelta(minutes=5)
        },
        auth.JWT_SECRET,
        algorithm=auth.JWT_ALGORITHM
    )

    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(valid_token)
    )

    assert response.status_code == 200

    # Создаём просроченный JWT с правильной подписью
    expired_token = jwt.encode(
        {
            "sub": str(user_id),
            "exp": datetime.datetime.now(
                datetime.timezone.utc
            ) - datetime.timedelta(minutes=5)
        },
        auth.JWT_SECRET,
        algorithm=auth.JWT_ALGORITHM
    )

    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(expired_token)
    )

    assert response.status_code == 401


def test_unsigned_jwt_is_rejected():
    """Сервер отклоняет JWT с алгоритмом none."""

    admin_token = login_user("test_first_admin")

    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(admin_token)
    )

    assert response.status_code == 200
    admin_id = response.json()["id"]

    # Создаём JWT без криптографической подписи
    unsigned_token = jwt.encode(
        {
            "sub": str(admin_id),
            "exp": datetime.datetime.now(
                datetime.timezone.utc
            ) + datetime.timedelta(minutes=5)
        },
        key=None,
        algorithm="none"
    )

    # Пытаемся использовать неподписанный JWT
    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(unsigned_token)
    )

    assert response.status_code == 401


def test_malformed_jwt_is_rejected():
    """Сервер отклоняет некорректный JWT."""

    malformed_token = "not-a-valid-jwt"

    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(malformed_token)
    )

    assert response.status_code == 401
    assert "detail" in response.json()

def test_missing_authorization_header():
    """Запрос без Authorization отклоняется."""

    response = httpx.get(
        f"{BASE_URL}/users/self"
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "authorization",
    [
        "Basic dGVzdDp0ZXN0",
        "Token some-invalid-token",
    ]
)
def test_unsupported_authorization_scheme(authorization):
    """API принимает только Bearer-аутентификацию."""

    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers={"Authorization": authorization}
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"sub": "not-a-number"},
        {"sub": "0"},
    ],
    ids=[
        "missing-sub",
        "invalid-sub",
        "nonexistent-user",
    ]
)
def test_jwt_with_invalid_subject_is_rejected(claims):
    """JWT с неправильным sub не даёт доступ."""

    payload = {
        "exp": datetime.datetime.now(
            datetime.timezone.utc
        ) + datetime.timedelta(minutes=5),
        **claims
    }

    token = jwt.encode(
        payload,
        auth.JWT_SECRET,
        algorithm=auth.JWT_ALGORITHM
    )

    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(token)
    )

    assert response.status_code == 401

@pytest.mark.parametrize(
    "username,password",
    [
        ("test_first_admin", "wrong-password"),
        ("nonexistent_auth_user_123", "password123"),
    ]
)
def test_invalid_login_credentials(username, password):
    """Неверные данные входа отклоняются."""

    response = httpx.post(
        f"{BASE_URL}/login",
        json={
            "username": username,
            "password": password
        }
    )

    assert response.status_code == 401

    # Не раскрываем, что именно было неверным
    assert response.json()["detail"] == (
        "Неверный логин или пароль"
    )


def test_password_hash_verification():
    """Пароль хешируется и правильно проверяется."""

    password = "secure_test_password_123"

    hashed = auth.hash_password(password)

    assert hashed != password
    assert auth.check_password(password, hashed)
    assert not auth.check_password(
        "incorrect_password", hashed
    )


def test_password_hash_uses_random_salt():
    """Одинаковые пароли получают разные хеши."""

    password = "same_test_password_123"

    hash_1 = auth.hash_password(password)
    hash_2 = auth.hash_password(password)

    assert hash_1 != hash_2

    assert auth.check_password(password, hash_1)
    assert auth.check_password(password, hash_2)


def test_jwt_without_exp_is_rejected():
    """JWT без срока действия отклоняется."""

    token = jwt.encode(
        {"sub": "1"},
        auth.JWT_SECRET,
        algorithm=auth.JWT_ALGORITHM,
    )

    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


def test_jwt_with_invalid_exp_is_rejected():
    """JWT с некорректным exp отклоняется."""

    token = jwt.encode(
        {
            "sub": "1",
            "exp": "invalid-timestamp",
        },
        auth.JWT_SECRET,
        algorithm=auth.JWT_ALGORITHM,
    )

    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


def test_jwt_with_future_nbf_is_rejected():
    """JWT нельзя использовать раньше времени nbf."""

    token = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.datetime.now(
                datetime.timezone.utc
            ) + datetime.timedelta(hours=2),
            "nbf": datetime.datetime.now(
                datetime.timezone.utc
            ) + datetime.timedelta(hours=1),
        },
        auth.JWT_SECRET,
        algorithm=auth.JWT_ALGORITHM,
    )

    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


def test_jwt_with_other_algorithm_is_rejected():
    """JWT с другим алгоритмом подписи отклоняется."""

    other_algorithm = (
        "HS384"
        if auth.JWT_ALGORITHM != "HS384"
        else "HS256"
    )

    token = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.datetime.now(
                datetime.timezone.utc
            ) + datetime.timedelta(minutes=5),
        },
        auth.JWT_SECRET,
        algorithm=other_algorithm,
    )

    response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


def test_jwt_role_claim_cannot_escalate_privileges():
    """Роль из JWT не должна заменять роль из БД."""

    user, _token = create_user_and_token(
        username="test_jwt_forged_role_user",
        email="test_jwt_forged_role_user@example.com",
    )

    assert user["role"] == "employee"

    token = jwt.encode(
        {
            "sub": str(user["id"]),
            "role": "admin",
            "exp": datetime.datetime.now(
                datetime.timezone.utc
            ) + datetime.timedelta(minutes=5),
        },
        auth.JWT_SECRET,
        algorithm=auth.JWT_ALGORITHM,
    )

    response = httpx.get(
        f"{BASE_URL}/users",
        headers=auth_headers(token),
    )

    assert response.status_code == 403

@pytest.mark.parametrize(
    "case_id, changes",
    [
        ("name_short", {"username": "abc"}),
        ("password_short", {"password": "1234567"}),
        ("email_bad", {"email": "not-an-email"}),
        ("phone_long", {"phone": "7" * 13}),
    ],
)
def test_registration_invalid_data(case_id, changes):
    """Регистрация с некорректными данными отклоняется."""

    payload = {
        "username": f"test_reg_{case_id}",
        "email": f"test_reg_{case_id}@example.com",
        "password": "password123",
        "phone": None,
    }

    payload.update(changes)

    response = httpx.post(
        f"{BASE_URL}/register",
        json=payload,
    )

    assert response.status_code == 422

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
    case_id, changes, expected_status
):

    """Некорректные изменения профиля отклоняются."""

    username = f"test_patch_{case_id}"

    user, token = create_user_and_token(
        username=username,
        email=f"{username}@example.com",
    )

    response = httpx.patch(
        f"{BASE_URL}/users/{user['id']}",
        headers=auth_headers(token),
        json=changes,
    )

    assert response.status_code == expected_status

    # Убеждаемся, что данные остались прежними
    profile_response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(token),
    )

    assert profile_response.status_code == 200

    profile = profile_response.json()

    assert profile["username"] == user["username"]
    assert profile["email"] == user["email"]
    assert profile["role"] == "employee"

def test_booking_invalid_date_format():
    """Неверный формат даты бронирования отклоняется."""

    token = login_user("test_first_admin")

    room_id, slot_id = get_first_available_slot(
        token, future_date(50)
    )

    response = httpx.post(
        f"{BASE_URL}/bookings",
        headers=auth_headers(token),
        json={
            "room_id": room_id,
            "time_window_id": slot_id,
            "date": "not-a-date",
        },
    )

    assert response.status_code == 422


def test_booking_past_date_is_rejected():
    """Нельзя забронировать комнату на прошедшую дату."""

    token = login_user("test_first_admin")

    room_id, slot_id = get_first_available_slot(
        token, future_date(50)
    )

    yesterday = (
        datetime.date.today()
        - datetime.timedelta(days=1)
    ).isoformat()

    response = httpx.post(
        f"{BASE_URL}/bookings",
        headers=auth_headers(token),
        json={
            "room_id": room_id,
            "time_window_id": slot_id,
            "date": yesterday,
        },
    )

    assert response.status_code == 400

def test_admin_cannot_set_role_to_null():
    """Администратор не может установить role=None."""

    admin_token = login_user("test_first_admin")

    profile_response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(admin_token),
    )

    assert profile_response.status_code == 200
    admin = profile_response.json()
    assert admin["role"] == "admin"

    response = httpx.patch(
        f"{BASE_URL}/users/{admin['id']}",
        headers=auth_headers(admin_token),
        json={"role": None},
    )

    assert response.status_code == 422

    # Проверяем, что роль не изменилась
    profile_response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(admin_token),
    )

    assert profile_response.status_code == 200
    assert profile_response.json()["role"] == "admin"

# ==========================================
# Дополнительные проверки валидации
# ==========================================

@pytest.mark.parametrize(
    "missing_field",
    ["username", "password", "email"]
)
def test_registration_required_fields(missing_field):
    """Обязательные поля регистрации нельзя пропускать."""

    payload = {
        "username": "test_missing_field_user",
        "password": "password123",
        "email": "missing_field@example.com",
    }

    del payload[missing_field]

    response = httpx.post(
        f"{BASE_URL}/register",
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "changes",
    [
        {"username": "u" * 51},
        {"password": "x" * 129},
    ],
    ids=["username-too-long", "password-too-long"]
)
def test_registration_field_max_lengths(changes):
    """Превышение максимальной длины отклоняется."""

    payload = {
        "username": "test_max_length_user",
        "password": "password123",
        "email": "max_length@example.com",
    }

    payload.update(changes)

    response = httpx.post(
        f"{BASE_URL}/register",
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.parametrize("length", [4, 50])
def test_registration_valid_username_boundaries(length):
    """Граничные допустимые длины username принимаются."""

    username = "v" * length

    response = httpx.post(
        f"{BASE_URL}/register",
        json={
            "username": username,
            "password": "password123",
            "email": f"boundary_{length}@example.com",
        },
    )

    assert response.status_code == 200
    assert response.json()["username"] == username
    assert response.json()["role"] == "employee"


@pytest.mark.parametrize(
    "endpoint",
    [
        "/users/not-an-id",
        "/rooms/not-an-id",
        "/bookings/not-an-id",
    ]
)
def test_invalid_path_identifiers(endpoint):
    """Некорректные идентификаторы в URL отклоняются."""

    token = login_user("test_first_admin")

    response = httpx.get(
        f"{BASE_URL}{endpoint}",
        headers=auth_headers(token),
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "field",
    ["room_id", "time_window_id"]
)
def test_booking_invalid_id_types(field):
    """Идентификаторы бронирования должны быть числами."""

    token = login_user("test_first_admin")

    payload = {
        "room_id": 1,
        "time_window_id": 1,
        "date": future_date(40),
    }

    payload[field] = "invalid-id"

    response = httpx.post(
        f"{BASE_URL}/bookings",
        headers=auth_headers(token),
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "case_id,password",
    [
        ("ascii", "x" * 73),
        ("unicode", "я" * 37),
    ]
)
def test_registration_password_byte_limit(case_id, password):
    """Пароли длиннее 72 байт отклоняются с HTTP 422."""

    response = httpx.post(
        f"{BASE_URL}/register",
        json={
            "username": f"test_bytes_{case_id}",
            "email": f"bytes_{case_id}@example.com",
            "password": password,
        },
    )

    assert response.status_code == 422


def test_login_overlong_password_is_rejected():
    """Слишком длинный пароль при входе не вызывает HTTP 500."""

    response = httpx.post(
        f"{BASE_URL}/login",
        json={
            "username": "test_first_admin",
            "password": "x" * 73,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Неверный логин или пароль"
    )


# ==========================================
# Задача 1.5. Обработка ошибок и транзакций
# ==========================================

@pytest.mark.parametrize(
    "field",
    ["username", "email", "phone"]
)
def test_duplicate_registration_returns_409(field):
    """Конфликт уникальности возвращает HTTP 409."""

    first = {
        "username": f"test_duplicate_{field}_first",
        "email": f"duplicate_{field}_first@example.com",
        "password": "password123",
        "phone": "79001112233" if field == "phone" else None,
    }

    second = {
        "username": f"test_duplicate_{field}_second",
        "email": f"duplicate_{field}_second@example.com",
        "password": "password123",
        "phone": "79001112233" if field == "phone" else None,
    }

    if field != "phone":
        second[field] = first[field]

    first_response = httpx.post(
        f"{BASE_URL}/register",
        json=first,
    )
    assert first_response.status_code == 200

    response = httpx.post(
        f"{BASE_URL}/register",
        json=second,
    )

    assert response.status_code == 409
    assert "detail" in response.json()

    # В ответе не должно быть внутренних подробностей БД
    detail = str(response.json()["detail"]).lower()

    for forbidden in (
        "sqlalchemy",
        "asyncpg",
        "duplicate key",
        "insert into",
        "traceback",
    ):
        assert forbidden not in detail

    # После конфликта приложение продолжает работать
    valid_response = httpx.post(
        f"{BASE_URL}/register",
        json={
            "username": f"test_after_conflict_{field}",
            "email": f"after_conflict_{field}@example.com",
            "password": "password123",
        },
    )

    assert valid_response.status_code == 200


@pytest.mark.parametrize(
    "field",
    ["username", "email"]
)
def test_conflicting_profile_update_preserves_data(field):
    """Неудачное обновление не меняет сохранённые данные."""

    user_1, _ = create_user_and_token(
        username=f"test_owner_{field}_one",
        email=f"owner_{field}_one@example.com",
    )

    user_2, token_2 = create_user_and_token(
        username=f"test_owner_{field}_two",
        email=f"owner_{field}_two@example.com",
    )

    # Пытаемся установить уже занятое значение
    response = httpx.patch(
        f"{BASE_URL}/users/{user_2['id']}",
        headers=auth_headers(token_2),
        json={field: user_1[field]},
    )

    assert response.status_code == 409

    # Проверяем состояние после неудачного обновления
    profile_response = httpx.get(
        f"{BASE_URL}/users/self",
        headers=auth_headers(token_2),
    )

    assert profile_response.status_code == 200
    assert profile_response.json()[field] == user_2[field]


def test_cannot_cancel_booking_twice():
    """Повторная отмена бронирования отклоняется."""

    _user, token = create_user_and_token(
        username="test_cancel_twice_user",
        email="cancel_twice_user@example.com",
    )

    booking = create_booking(token, future_date(70))

    endpoint = (
        f"{BASE_URL}/bookings/cancel/{booking['id']}"
    )

    first_response = httpx.patch(
        endpoint,
        headers=auth_headers(token),
    )
    assert first_response.status_code == 200

    second_response = httpx.patch(
        endpoint,
        headers=auth_headers(token),
    )
    assert second_response.status_code == 400

    # Бронирование осталось отменённым
    response = httpx.get(
        f"{BASE_URL}/bookings/{booking['id']}",
        headers=auth_headers(token),
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
    ]
)
def test_nonexistent_objects_return_404(method, path):
    """Несуществующий объект возвращает HTTP 404."""

    admin_token = login_user("test_first_admin")

    response = httpx.request(
        method,
        f"{BASE_URL}{path}",
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 404
    assert "detail" in response.json()


# ==========================================
# Задача 1.6. Безопасность бронирований
# ==========================================

@pytest.mark.parametrize(
    "field, invalid_id",
    [
        ("room_id", -1),
        ("room_id", 999999999),
        ("time_window_id", -1),
        ("time_window_id", 999999999),
    ],
)
def test_booking_invalid_references(field, invalid_id):
    """Некорректные ссылки на комнату и слот отклоняются."""

    token = login_user("test_first_admin")
    date = future_date(100)

    room_id, slot_id = get_first_available_slot(
        token, date
    )

    payload = {
        "room_id": room_id,
        "time_window_id": slot_id,
        "date": date,
    }

    payload[field] = invalid_id

    response = httpx.post(
        f"{BASE_URL}/bookings",
        headers=auth_headers(token),
        json=payload,
    )

    assert response.status_code == 400


def test_booking_slot_from_another_room():
    """Нельзя использовать слот другой комнаты."""

    token = login_user("test_first_admin")
    date = future_date(101)

    room_id, slot_id = get_first_available_slot(
        token, date
    )

    rooms_response = httpx.get(
        f"{BASE_URL}/rooms",
        headers=auth_headers(token),
    )

    assert rooms_response.status_code == 200

    rooms = rooms_response.json()["rooms"]

    other_room_id = next(
        room["id"]
        for room in rooms
        if room["id"] != room_id
    )

    response = httpx.post(
        f"{BASE_URL}/bookings",
        headers=auth_headers(token),
        json={
            "room_id": other_room_id,
            "time_window_id": slot_id,
            "date": date,
        },
    )

    assert response.status_code == 400


def test_slot_availability_after_booking_and_cancellation():
    """Доступность слота изменяется при брони и отмене."""

    _user, token = create_user_and_token(
        username="test_slot_availability_user",
        email="slot_availability_user@example.com",
    )

    date = future_date(102)
    room_id, slot_id = get_first_available_slot(
        token, date
    )

    def slot_is_available():
        response = httpx.get(
            f"{BASE_URL}/rooms/available/{date}",
            headers=auth_headers(token),
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

    # Изначально слот свободен
    assert slot_is_available()

    # Бронируем слот
    booking_response = httpx.post(
        f"{BASE_URL}/bookings",
        headers=auth_headers(token),
        json={
            "room_id": room_id,
            "time_window_id": slot_id,
            "date": date,
        },
    )

    assert booking_response.status_code == 200
    booking_id = booking_response.json()["id"]

    # Забронированный слот больше не доступен
    assert not slot_is_available()

    # Отменяем бронирование
    cancel_response = httpx.patch(
        f"{BASE_URL}/bookings/cancel/{booking_id}",
        headers=auth_headers(token),
    )

    assert cancel_response.status_code == 200

    # Слот снова свободен
    assert slot_is_available()


def test_concurrent_booking_only_one_succeeds():
    """Два пользователя не могут занять один слот."""

    _user_1, token_1 = create_user_and_token(
        username="test_concurrent_booking_one",
        email="concurrent_booking_one@example.com",
    )

    _user_2, token_2 = create_user_and_token(
        username="test_concurrent_booking_two",
        email="concurrent_booking_two@example.com",
    )

    date = future_date(103)
    room_id, slot_id = get_first_available_slot(
        token_1, date
    )

    payload = {
        "room_id": room_id,
        "time_window_id": slot_id,
        "date": date,
    }

    def try_book(token):
        return httpx.post(
            f"{BASE_URL}/bookings",
            headers=auth_headers(token),
            json=payload,
            timeout=20,
        )

    # Отправляем запросы из двух потоков
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(try_book, [token_1, token_2])
        )

    statuses = sorted(
        response.status_code for response in responses
    )

    # Только одно бронирование должно быть успешным
    assert statuses == [200, 409]

    # Проверяем итоговое состояние PostgreSQL через API
    admin_token = login_user("test_first_admin")

    response = httpx.get(
        f"{BASE_URL}/bookings/all",
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


def test_inactive_room_cannot_be_booked():
    """Неактивная комната недоступна для бронирования."""

    # Защита от случайного изменения основной БД
    assert config.POSTGRES_DB == "test_db"
    assert config.POSTGRES_HOST == "test_db"

    token = login_user("test_first_admin")
    date = future_date(120)

    async def scenario():
        # Создаём отдельную неактивную комнату
        async with AsyncSessionLocal() as session:
            room = models.Room(
                room_name="Inactive test room",
                description="Security test",
                is_active=False,
            )
            session.add(room)
            await session.flush()

            slot = models.TimeWindow(
                room_id=room.id,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(12, 0),
            )
            session.add(slot)
            await session.flush()

            room_id = room.id
            slot_id = slot.id

            await session.commit()

        try:
            # Неактивная комната не должна
            # присутствовать среди доступных
            response = httpx.get(
                f"{BASE_URL}/rooms/available/{date}",
                headers=auth_headers(token),
            )

            assert response.status_code == 200

            available_room_ids = [
                item["id"]
                for item in response.json()["rooms"]
            ]

            assert room_id not in available_room_ids

            # Прямой запрос на бронирование
            # также должен быть отклонён
            response = httpx.post(
                f"{BASE_URL}/bookings",
                headers=auth_headers(token),
                json={
                    "room_id": room_id,
                    "time_window_id": slot_id,
                    "date": date,
                },
            )

            assert response.status_code == 400

        finally:
            # Удаляем только созданные тестом записи
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(models.Booking).where(
                        models.Booking.room_id == room_id
                    )
                )

                await session.execute(
                    delete(models.TimeWindow).where(
                        models.TimeWindow.id == slot_id
                    )
                )

                await session.execute(
                    delete(models.Room).where(
                        models.Room.id == room_id
                    )
                )

                await session.commit()


    async def run_with_disposal():
        try:
            await scenario()
        finally:
            await engine.dispose()

    asyncio.run(run_with_disposal())