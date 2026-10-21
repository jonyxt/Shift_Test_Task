"""Тесты: test_users."""


from tests.integration.helpers import auth_headers


def test_get_current_user(api_client, create_test_user):
    """Проверяет получение профиля текущего пользователя."""

    user, token = create_test_user()

    response = api_client.get(
        "/users/self",
        headers=auth_headers(token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == user["id"]
    assert data["username"] == user["username"]
    assert data["email"] == user["email"]


def test_admin_can_get_users(api_client, admin_token):
    """Администратор получает список пользователей."""

    response = api_client.get(
        "/users",
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200

    users = response.json()["users"]

    assert isinstance(users, list)
    assert len(users) > 0


def test_admin_can_get_user_by_id(
    api_client, admin_token, create_test_user
):
    """Администратор получает пользователя по ID."""

    user, _ = create_test_user()

    response = api_client.get(
        f"/users/{user['id']}",
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == user["id"]
    assert data["username"] == user["username"]
    assert data["email"] == user["email"]


def test_user_can_update_self(api_client, create_test_user):
    """Пользователь изменяет собственный профиль."""

    user, token = create_test_user()

    # Формируем уникальный номер на основе ID пользователя.
    phone = f"79{user['id']:09d}"

    response = api_client.patch(
        f"/users/{user['id']}",
        headers=auth_headers(token),
        json={"phone": phone},
    )

    assert response.status_code == 200
    assert response.json()["id"] == user["id"]
    assert response.json()["phone"] == phone


def test_employee_cannot_update_other_user(
    api_client, create_test_user
):
    """Сотрудник не может изменить чужой профиль."""

    _, token = create_test_user()
    other_user, _ = create_test_user()

    response = api_client.patch(
        f"/users/{other_user['id']}",
        headers=auth_headers(token),
        json={"phone": "78888888888"},
    )

    assert response.status_code == 403


def test_employee_cannot_get_users(
    api_client, create_test_user
):
    """Сотрудник не может получить список пользователей."""

    _, token = create_test_user()

    response = api_client.get(
        "/users",
        headers=auth_headers(token),
    )

    assert response.status_code == 403


def test_employee_cannot_assign_admin_role_to_self(
    api_client, create_test_user
):
    """Сотрудник не может повысить собственные права."""

    user, token = create_test_user()

    assert user["role"] == "employee"

    response = api_client.patch(
        f"/users/{user['id']}",
        headers=auth_headers(token),
        json={"role": "admin"},
    )

    assert response.status_code == 403

    profile_response = api_client.get(
        "/users/self",
        headers=auth_headers(token),
    )

    assert profile_response.status_code == 200
    assert profile_response.json()["role"] == "employee"


def test_employee_cannot_get_other_user_by_id(
    api_client, create_test_user
):
    """Сотрудник не может прочитать чужой профиль."""

    user_1, token_1 = create_test_user()
    user_2, _ = create_test_user()

    assert user_1["id"] != user_2["id"]

    response = api_client.get(
        f"/users/{user_2['id']}",
        headers=auth_headers(token_1),
    )

    assert response.status_code == 403


def test_admin_can_change_user_role(
    api_client, admin_token, create_test_user
):
    """Администратор может назначать и отзывать роль admin."""

    user, _ = create_test_user()

    assert user["role"] == "employee"

    headers = auth_headers(admin_token)
    path = f"/users/{user['id']}"

    response = api_client.patch(
        path,
        headers=headers,
        json={"role": "admin"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"

    try:
        response = api_client.get(
            path,
            headers=headers,
        )

        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    finally:
        # Возвращаем исходную роль даже при ошибке проверки.
        restore_response = api_client.patch(
            path,
            headers=headers,
            json={"role": "employee"},
        )

        assert restore_response.status_code == 200
        assert restore_response.json()["role"] == "employee"


def test_cannot_demote_last_admin(api_client, admin_token):
    """Нельзя снять роль у последнего администратора."""

    headers = auth_headers(admin_token)

    response = api_client.get(
        "/users/self",
        headers=headers,
    )

    assert response.status_code == 200
    admin = response.json()
    assert admin["role"] == "admin"

    users_response = api_client.get(
        "/users",
        headers=headers,
    )

    assert users_response.status_code == 200

    admins = [
        user for user in users_response.json()["users"]
        if user["role"] == "admin"
    ]

    assert len(admins) == 1
    assert admins[0]["id"] == admin["id"]

    response = api_client.patch(
        f"/users/{admin['id']}",
        headers=headers,
        json={"role": "employee"},
    )

    assert response.status_code == 400

    response = api_client.get(
        "/users/self",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
