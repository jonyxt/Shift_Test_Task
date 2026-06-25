"""Настройка подключения к базе данных.

Модуль создает асинхронный SQLAlchemy engine, фабрику асинхронных сессий
и базовый класс для ORM-моделей приложения.
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from .config import config


engine = create_async_engine(config.DATABASE_URL)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()