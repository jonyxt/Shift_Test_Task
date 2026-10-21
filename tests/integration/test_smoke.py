"""Тесты: test_smoke."""


def test_openapi_is_available(api_client):
    """Проверяет доступность OpenAPI-схемы."""

    response = api_client.get("/openapi.json")

    assert response.status_code == 200
    assert "paths" in response.json()
