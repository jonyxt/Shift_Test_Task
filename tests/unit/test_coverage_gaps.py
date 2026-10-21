"""Targeted unit tests for uncovered security, initialization and CLI branches."""

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.exc import IntegrityError

from app import auth, schemas, services
from app import bootstrap_admin


@pytest.mark.asyncio
async def test_valid_token_for_missing_user_returns_401():
    """A correctly signed token must not authorize a deleted user."""
    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=auth.create_access_token(999_999_999),
    )

    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user(credentials, session)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Неверный или просроченный токен"
    session.scalar.assert_awaited_once()


@pytest.mark.asyncio
async def test_existing_rooms_are_not_seeded_again():
    """Do not add another set of rooms if the database is already seeded."""
    session = MagicMock()
    session.scalar = AsyncMock(return_value=3)
    session.commit = AsyncMock()

    await services.initial_rooms_and_time_windows(session)

    session.scalar.assert_awaited_once()
    session.add.assert_not_called()
    session.add_all.assert_not_called()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_initial_admin_integrity_error_is_safe():
    """DB uniqueness errors should become a controlled ValueError."""
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=IntegrityError("SELECT", {}, Exception("duplicate"))
    )
    data = schemas.RegisterRequest(
        username="test_cli_admin",
        email="test_cli_admin@example.com",
        password="password123",
    )

    with pytest.raises(ValueError, match="Пользователь с такими данными"):
        await bootstrap_admin.create_initial_admin(session, data)

    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_save_admin_always_disposes_engine(monkeypatch):
    """An async SQLAlchemy engine must be disposed with await."""
    session = MagicMock()
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=False)

    fake_engine = SimpleNamespace(dispose=AsyncMock())
    fake_create = AsyncMock(return_value=42)

    monkeypatch.setattr(bootstrap_admin, "AsyncSessionLocal", lambda: manager)
    monkeypatch.setattr(bootstrap_admin, "create_initial_admin", fake_create)
    monkeypatch.setattr(bootstrap_admin, "engine", fake_engine)

    data = schemas.RegisterRequest(
        username="test_cli_admin",
        email="test_cli_admin@example.com",
        password="password123",
    )

    result = await bootstrap_admin.save_admin(data)

    assert result == 42
    fake_create.assert_awaited_once_with(session, data)
    fake_engine.dispose.assert_awaited_once()


def _prepare_interactive_cli(monkeypatch, username="test_cli_admin"):
    """Provide controlled console input without touching real stdin."""
    fake_sys = SimpleNamespace(
        stdin=SimpleNamespace(isatty=lambda: True),
        stderr=io.StringIO(),
    )
    monkeypatch.setattr(bootstrap_admin, "sys", fake_sys)
    answers = iter([username, "test_cli_admin@example.com"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(bootstrap_admin, "getpass", lambda prompt: "password123")


def test_admin_cli_rejects_noninteractive_terminal(monkeypatch):
    fake_sys = SimpleNamespace(
        stdin=SimpleNamespace(isatty=lambda: False),
        stderr=io.StringIO(),
    )
    monkeypatch.setattr(bootstrap_admin, "sys", fake_sys)
    save = AsyncMock()
    monkeypatch.setattr(bootstrap_admin, "save_admin", save)

    assert bootstrap_admin.main() == 1
    assert "интерактивный терминал" in fake_sys.stderr.getvalue()
    save.assert_not_awaited()


def test_admin_cli_rejects_invalid_input(monkeypatch, capsys):
    _prepare_interactive_cli(monkeypatch, username="abc")
    save = AsyncMock()
    monkeypatch.setattr(bootstrap_admin, "save_admin", save)

    assert bootstrap_admin.main() == 1
    assert "Некорректные данные" in capsys.readouterr().out
    save.assert_not_awaited()


def test_admin_cli_creates_admin(monkeypatch, capsys):
    _prepare_interactive_cli(monkeypatch)
    save = AsyncMock(return_value=42)
    monkeypatch.setattr(bootstrap_admin, "save_admin", save)

    assert bootstrap_admin.main() == 0
    assert "Администратор создан. ID: 42" in capsys.readouterr().out
    save.assert_awaited_once()
    assert save.await_args.args[0].username == "test_cli_admin"


@pytest.mark.parametrize(
    "error, message",
    [
        (
            bootstrap_admin.AdminAlreadyInitialized("Администратор уже существует"),
            "Администратор уже существует",
        ),
        (ValueError("Конфликт данных"), "Конфликт данных"),
    ],
)
def test_admin_cli_handles_creation_failure(monkeypatch, capsys, error, message):
    _prepare_interactive_cli(monkeypatch)
    save = AsyncMock(side_effect=error)
    monkeypatch.setattr(bootstrap_admin, "save_admin", save)

    assert bootstrap_admin.main() == 1
    assert message in capsys.readouterr().out
    save.assert_awaited_once()
