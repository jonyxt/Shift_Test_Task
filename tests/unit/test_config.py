
"""Unit-тесты конфигурации приложения."""

import pytest

from pydantic import ValidationError
from app.config import Settings, get_settings


VALID_CONFIG = {
    "POSTGRES_USER": "test_user",
    "POSTGRES_PASSWORD": "test_password",
    "POSTGRES_DB": "test_db",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": 5432,
    "JWT_SECRET": "x" * 32,
    "JWT_ALGORITHM": "HS256",
    "JWT_EXP_DELTA_SECONDS": 3600,
}


def make_settings(**overrides):
    """Создаёт настройки без чтения .env-файла."""
    return Settings(
        _env_file=None,
        **(VALID_CONFIG | overrides),
    )


def test_valid_settings():
    settings = make_settings()

    assert settings.POSTGRES_DB == "test_db"
    assert settings.POSTGRES_PORT == 5432
    assert settings.JWT_ALGORITHM == "HS256"
    assert settings.JWT_EXP_DELTA_SECONDS == 3600


def test_database_url():
    settings = make_settings(
        POSTGRES_PASSWORD="pass@word:/?#"
    )

    url = settings.DATABASE_URL

    assert url.drivername == "postgresql+asyncpg"
    assert url.username == "test_user"
    assert url.password == "pass@word:/?#"
    assert url.host == "localhost"
    assert url.port == 5432
    assert url.database == "test_db"


def test_short_jwt_secret_rejected():
    with pytest.raises(ValidationError):
        make_settings(JWT_SECRET="short")


@pytest.mark.parametrize(
    "port",
    [0, -1, 65536, "invalid"],
)
def test_invalid_postgres_port_rejected(port):
    with pytest.raises(ValidationError):
        make_settings(POSTGRES_PORT=port)


def test_invalid_jwt_algorithm_rejected():
    with pytest.raises(ValidationError):
        make_settings(JWT_ALGORITHM="none")


def test_invalid_jwt_expiration_rejected():
    with pytest.raises(ValidationError):
        make_settings(JWT_EXP_DELTA_SECONDS=0)


def test_settings_cache():
    assert get_settings() is get_settings()


def test_secrets_hidden_in_repr():
    settings = make_settings()

    assert "test_password" not in repr(settings)
    assert ("x" * 32) not in repr(settings)


def test_default_environment():
    settings = make_settings()

    assert settings.APP_ENV == "dev"


def test_valid_test_environment():
    settings = make_settings(
        APP_ENV="test",
        POSTGRES_DB="test_db",
        POSTGRES_HOST="test_db",
    )

    assert settings.APP_ENV == "test"


def test_test_environment_rejects_working_db():
    with pytest.raises(ValidationError):
        make_settings(
            APP_ENV="test",
            POSTGRES_DB="booking_db",
            POSTGRES_HOST="db",
        )


def test_production_rejects_test_db():
    with pytest.raises(ValidationError):
        make_settings(
            APP_ENV="prod",
            POSTGRES_DB="test_db",
            POSTGRES_HOST="test_db",
        )


def test_production_rejects_default_password():
    with pytest.raises(ValidationError):
        make_settings(
            APP_ENV="prod",
            POSTGRES_DB="booking_db",
            POSTGRES_HOST="db",
            POSTGRES_PASSWORD="postgres",
        )


def test_unknown_environment_rejected():
    with pytest.raises(ValidationError):
        make_settings(APP_ENV="staging")
