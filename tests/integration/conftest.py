"""Подготовка БД только для интеграционных тестов."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _integration_database(prepare_test_database):
    """Гарантирует чистую тестовую БД для интеграционного набора."""
    return None
