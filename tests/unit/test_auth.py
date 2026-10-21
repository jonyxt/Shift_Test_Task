"""Тесты: test_auth."""


from app import auth


def test_password_hash_verification():
    """Пароль хешируется и корректно проверяется."""

    password = "secure_test_password_123"

    hashed = auth.hash_password(password)

    assert hashed != password
    assert auth.check_password(password, hashed)
    assert not auth.check_password(
        "incorrect_password", hashed
    )


def test_password_hash_uses_random_salt():
    """Одинаковые пароли получают разные хеши."""

    password = "same_test_password_123"

    hash_1 = auth.hash_password(password)
    hash_2 = auth.hash_password(password)

    assert hash_1 != hash_2

    assert auth.check_password(password, hash_1)
    assert auth.check_password(password, hash_2)
