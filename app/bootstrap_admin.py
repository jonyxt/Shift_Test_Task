import asyncio
import sys
from getpass import getpass

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from watchfiles import awatch

from . import auth, models, schemas
from .database import AsyncSessionLocal, engine


class AdminAlreadyInitialized(Exception):
    """Администратор уже существует."""


async def create_initial_admin(
        session: AsyncSession,
        user_data: schemas.RegisterRequest
) -> int:
    """Создает первого администратора в отдельной транзакции"""

    try:
        async with session.begin():
            """
            Защита от одновременного запуска двух CLI-команд.
            PostgreSQL удерживает блокировку до конца транзакции
            """
            await session.execute(
                text('SELECT pg_advisory_xact_lock(812741097)')
            )

            existing_admin = await session.scalar(
                select(models.User.id)
                .where(models.User.role == models.UserRole.ADMIN)
                .limit(1)
            )

            if existing_admin is not None:
                raise AdminAlreadyInitialized(
                    'Администратор уже существует'
                )

            admin = models.User(
                username=user_data.username,
                hashed_password=auth.hash_password(
                    user_data.password
                ),
                email=user_data.email,
                phone=user_data.phone,
                role=models.UserRole.ADMIN
            )

            session.add(admin)
            await session.flush()

            admin_id = admin.id

        return admin_id

    except IntegrityError as exc:
        raise ValueError(
            'Пользователь с такими данными уже существует'
        ) from exc

async def save_admin(user_data: schemas.RegisterRequest) -> int:
    try:
        async with AsyncSessionLocal() as session:
            return await create_initial_admin(session, user_data)
    finally:
        engine.dispose()

def main() -> int:
    """Интерактивное создание первого администратора."""

    if not sys.stdin.isatty():
        print(
            "Для создания администратора нужен интерактивный терминал.",
            file=sys.stderr
        )
        return 1

    try:
        username = input("Имя администратора: ").strip()
        email = input("Email: ").strip()
        password = getpass("Пароль: ")

        user_data = schemas.RegisterRequest(
            username=username,
            email=email,
            password=password
        )

    except (ValidationError, ValueError):
        print("Некорректные данные администратора.")
        return 1

    try:
        admin_id = asyncio.run(save_admin(user_data))

    except AdminAlreadyInitialized as exc:
        print(str(exc))
        return 1

    except ValueError as exc:
        print(str(exc))
        return 1

    print(f"Администратор создан. ID: {admin_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())