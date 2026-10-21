"""Общие вспомогательные функции интеграционных тестов."""


import os
import datetime


BASE_URL = os.getenv('BASE_URL', 'http://app:8000')


def auth_headers(token: str) -> dict:
    """Формирует заголовок Authorization для запросов с JWT-токеном."""

    return {
        'Authorization': f"Bearer {token}"
    }


def future_date(days: int = 1) -> str:
    """Возвращает дату на указанное количество дней позже текущей даты."""

    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()
