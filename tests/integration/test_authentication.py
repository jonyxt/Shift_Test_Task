"""Тесты: test_authentication."""


import datetime
import jwt
import pytest
from uuid import uuid4
from app import auth
from tests.integration.helpers import auth_headers


def test_login_user(api_client, registration_payload):
    """Проверяет успешную авторизацию пользователя."""

    register_response = api_client.post(
        "/register",
        json=registration_payload,
    )

    assert register_response.status_code == 200

    response = api_client.post(
        "/login",
        json={
            "username": registration_payload["username"],
            "password": registration_payload["password"],
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 0


def test_tampered_jwt_signature_is_rejected(
    api_client, admin_token
):
    """Изменение подписи JWT делает токен недействительным."""

    response = api_client.get(
        "/users/self",
        headers=auth_headers(admin_token),
    )
    assert response.status_code == 200

    header, payload, signature = admin_token.split(".")

    changed_char = "A" if signature[0] != "A" else "B"

    fake_token = (
        f"{header}.{payload}."
        f"{changed_char}{signature[1:]}"
    )

    response = api_client.get(
        "/users/self",
        headers=auth_headers(fake_token),
    )

    assert response.status_code == 401


def test_expired_jwt_is_rejected(
    api_client, admin_token, signed_jwt
):
    """JWT с истёкшим сроком действия отклоняется."""

    response = api_client.get(
        "/users/self",
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    user_id = response.json()["id"]

    now = datetime.datetime.now(datetime.timezone.utc)

    valid_token = signed_jwt({
        "sub": str(user_id),
        "exp": now + datetime.timedelta(minutes=5),
    })

    response = api_client.get(
        "/users/self",
        headers=auth_headers(valid_token),
    )

    assert response.status_code == 200

    expired_token = signed_jwt({
        "sub": str(user_id),
        "exp": now - datetime.timedelta(minutes=5),
    })

    response = api_client.get(
        "/users/self",
        headers=auth_headers(expired_token),
    )

    assert response.status_code == 401


def test_unsigned_jwt_is_rejected(api_client, admin_token):
    """Сервер отклоняет JWT с алгоритмом none."""

    response = api_client.get(
        "/users/self",
        headers=auth_headers(admin_token),
    )

    assert response.status_code == 200
    admin_id = response.json()["id"]

    unsigned_token = jwt.encode(
        {
            "sub": str(admin_id),
            "exp": (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=5)
            ),
        },
        key=None,
        algorithm="none",
    )

    response = api_client.get(
        "/users/self",
        headers=auth_headers(unsigned_token),
    )

    assert response.status_code == 401


def test_malformed_jwt_is_rejected(api_client):
    """Некорректный JWT отклоняется."""

    response = api_client.get(
        "/users/self",
        headers=auth_headers("not-a-valid-jwt"),
    )

    assert response.status_code == 401
    assert "detail" in response.json()


def test_missing_authorization_header(api_client):
    """Запрос без Authorization отклоняется."""

    response = api_client.get("/users/self")

    assert response.status_code == 401


@pytest.mark.parametrize(
    "authorization",
    [
        "Basic dGVzdDp0ZXN0",
        "Token some-invalid-token",
    ],
)
def test_unsupported_authorization_scheme(
    api_client, authorization
):
    """API принимает только Bearer-аутентификацию."""

    response = api_client.get(
        "/users/self",
        headers={"Authorization": authorization},
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
    ],
)
def test_jwt_with_invalid_subject_is_rejected(
    api_client, signed_jwt, claims
):
    """JWT с неправильным sub не даёт доступ."""

    payload = {
        "exp": (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(minutes=5)
        ),
        **claims,
    }

    token = signed_jwt(payload)

    response = api_client.get(
        "/users/self",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "case",
    ["wrong_password", "unknown_user"],
)
def test_invalid_login_credentials(api_client, case):
    """Неверные данные входа отклоняются."""

    if case == "wrong_password":
        username = "test_first_admin"
        password = "wrong-password"
    else:
        username = f"missing_{uuid4().hex[:12]}"
        password = "password123"

    response = api_client.post(
        "/login",
        json={
            "username": username,
            "password": password,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Неверный логин или пароль"
    )


def test_jwt_without_exp_is_rejected(
    api_client, signed_jwt
):
    """JWT без срока действия отклоняется."""

    token = signed_jwt({"sub": "1"})

    response = api_client.get(
        "/users/self",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


def test_jwt_with_invalid_exp_is_rejected(
    api_client, signed_jwt
):
    """JWT с некорректным exp отклоняется."""

    token = signed_jwt({
        "sub": "1",
        "exp": "invalid-timestamp",
    })

    response = api_client.get(
        "/users/self",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


def test_jwt_with_future_nbf_is_rejected(
    api_client, signed_jwt
):
    """JWT нельзя использовать раньше времени nbf."""

    now = datetime.datetime.now(datetime.timezone.utc)

    token = signed_jwt({
        "sub": "1",
        "exp": now + datetime.timedelta(hours=2),
        "nbf": now + datetime.timedelta(hours=1),
    })

    response = api_client.get(
        "/users/self",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


def test_jwt_with_other_algorithm_is_rejected(
    api_client, signed_jwt
):
    """JWT с другим алгоритмом подписи отклоняется."""

    other_algorithm = (
        "HS384"
        if auth.JWT_ALGORITHM != "HS384"
        else "HS256"
    )

    token = signed_jwt(
        {
            "sub": "1",
            "exp": (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=5)
            ),
        },
        algorithm=other_algorithm,
    )

    response = api_client.get(
        "/users/self",
        headers=auth_headers(token),
    )

    assert response.status_code == 401


def test_jwt_role_claim_cannot_escalate_privileges(
    api_client, create_test_user, signed_jwt
):
    """Роль из JWT не должна заменять роль из БД."""

    user, _ = create_test_user()

    assert user["role"] == "employee"

    token = signed_jwt({
        "sub": str(user["id"]),
        "role": "admin",
        "exp": (
            datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(minutes=5)
        ),
    })

    response = api_client.get(
        "/users",
        headers=auth_headers(token),
    )

    assert response.status_code == 403


def test_login_overlong_password_is_rejected(api_client):
    """Слишком длинный пароль при входе не вызывает HTTP 500."""

    response = api_client.post(
        "/login",
        json={
            "username": "test_first_admin",
            "password": "x" * 73,
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Неверный логин или пароль"
    )
