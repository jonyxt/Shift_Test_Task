"""Тесты: test_registration."""


def test_register_cannot_choose_admin_role(
    api_client, registration_payload
):
    """Пользователь не может назначить себе роль admin."""

    response = api_client.post(
        "/register",
        json={
            **registration_payload,
            "role": "admin",
        },
    )

    assert response.status_code == 200
    assert response.json()["role"] == "employee"


def test_register_user(api_client, registration_payload):
    """Проверяет успешную регистрацию пользователя."""

    response = api_client.post(
        "/register",
        json=registration_payload,
    )

    assert response.status_code == 200

    data = response.json()

    assert data["username"] == registration_payload["username"]
    assert data["email"] == registration_payload["email"]
    assert data["role"] == "employee"
    assert "id" in data
    assert "hashed_password" not in data
