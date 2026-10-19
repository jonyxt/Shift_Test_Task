"""Аутентификация и авторизация пользователей.

Модуль содержит функции для хеширования паролей, проверки паролей,
создания и декодирования JWT-токенов, а также FastAPI dependencies
для получения текущего пользователя и проверки прав администратора.
"""
import os

import jwt
import bcrypt

from typing import Annotated
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import models
from .dependencies import get_db_session


JWT_SECRET = os.getenv('JWT_SECRET')
if not JWT_SECRET:
    raise ValueError('JWT_SECRET не задан')
if len(JWT_SECRET.encode("utf-8")) < 32:
    raise ValueError(
        "JWT_SECRET должен содержать не менее 32 байт"
    )
JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')
JWT_EXP_DELTA_SECONDS = int(os.getenv('JWT_EXP_DELTA_SECONDS', '3600'))

bearer_scheme = HTTPBearer()

def hash_password(password: str) -> str:
    """Хеширует пароль пользователя с помощью bcrypt.

    Args:
        password: Пароль в открытом виде.

    Returns:
        Строковое представление bcrypt-хеша, пригодное для хранения в базе данных.
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def check_password(password: str, hashed_password: str) -> bool:
    """Проверяет пароль пользователя по сохраненному bcrypt-хешу.

    Args:
        password: Пароль в открытом виде.
        hashed_password: Хеш пароля из базы данных.

    Returns:
        True, если пароль соответствует хешу, иначе False.
    """
    password_bytes = password.encode("utf-8")

    if len(password_bytes) > 72:
        return False

    return bcrypt.checkpw(
        password_bytes,
        hashed_password.encode("utf-8")
    )

def create_access_token(user_id: int) -> str:
    """Создает JWT access token для пользователя.

    В payload записывается идентификатор пользователя в поле `sub` и время
    истечения токена в поле `exp`.

    Args:
        user_id: Идентификатор пользователя.

    Returns:
        Закодированный JWT-токен.
    """
    expire = datetime.now(timezone.utc) + timedelta(seconds=JWT_EXP_DELTA_SECONDS)
    payload = {
        'sub': str(user_id),
        'exp': expire,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> dict:
    """Декодирует и валидирует JWT access token.

    Args:
        token: JWT-токен из заголовка Authorization.

    Returns:
        Payload токена.

    Raises:
        jwt.InvalidTokenError: Если токен некорректен.
        jwt.ExpiredSignatureError: Если срок действия токена истек.
    """
    return jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["exp", "sub"]},
    )

async def get_current_user(
        credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
        session: Annotated[AsyncSession, Depends(get_db_session)]
) -> models.User:
    """Возвращает текущего пользователя по Bearer-токену.

    Dependency извлекает JWT из заголовка Authorization, валидирует его,
    получает пользователя из базы данных и возвращает ORM-объект User.

    Raises:
        HTTPException: 401, если токен отсутствует, некорректен, истек
        или пользователь из токена не найден.
    """
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get('sub'))
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Неверный или просроченный токен'
        )
    query = select(models.User).where(models.User.id == user_id)
    user = await session.scalar(query)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Неверный или просроченный токен'
        )
    return user

CurrentUserDep = Annotated[models.User, Depends(get_current_user)]

async def require_admin(current_user: CurrentUserDep) -> models.User:
    """Проверяет, что текущий пользователь является администратором.

    Args:
        current_user: Пользователь, полученный через зависимость CurrentUserDep.

    Returns:
        Текущий пользователь, если у него роль admin.

    Raises:
        HTTPException: 403, если у пользователя недостаточно прав.
    """
    if current_user.role != models.UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Недостаточно прав'
        )
    return current_user

AdminUserDep = Annotated[models.User, Depends(require_admin)]