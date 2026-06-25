"""Конфигурация приложения.

Модуль загружает переменные окружения из `.env` для локального запуска,
проверяет обязательные настройки PostgreSQL и собирает строку подключения
для асинхронного SQLAlchemy engine.
"""
import os
from dotenv import load_dotenv


load_dotenv()


class Config:
    """Настройки подключения к базе данных.

    Атрибуты класса читаются из переменных окружения при импорте модуля.
    Если хотя бы одна обязательная переменная PostgreSQL отсутствует,
    при создании конфигурации будет выброшено исключение ValueError.
    """

    POSTGRES_USER = os.getenv('POSTGRES_USER')
    POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
    POSTGRES_DB = os.getenv('POSTGRES_DB')
    POSTGRES_HOST = os.getenv('POSTGRES_HOST')
    POSTGRES_PORT = os.getenv('POSTGRES_PORT')

    if (not POSTGRES_USER
        or not POSTGRES_DB
        or not POSTGRES_PORT
        or not POSTGRES_HOST
        or not POSTGRES_PASSWORD):
        raise ValueError('Проверьте переменные окружения')

    DATABASE_URL = (f'postgresql+asyncpg://'
                    f'{POSTGRES_USER}:{POSTGRES_PASSWORD}@'
                    f'{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}')

config = Config()