from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Настройки приложения из переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    APP_ENV: Literal["dev", "test", "prod"] = "dev"

    POSTGRES_USER: str = Field(min_length=1)
    POSTGRES_PASSWORD: str = Field(min_length=1, repr=False)
    POSTGRES_DB: str = Field(min_length=1)
    POSTGRES_HOST: str = Field(min_length=1)
    POSTGRES_PORT: int = Field(ge=1, le=65535)

    JWT_SECRET: str = Field(repr=False)
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    JWT_EXP_DELTA_SECONDS: int = Field(default=3600, gt=0)

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        if len(value.encode("utf-8")) < 32:
            raise ValueError(
                "JWT_SECRET должен содержать не менее 32 байт"
            )
        return value


    @model_validator(mode="after")
    def validate_environment(self):
        """Проверяет безопасность настроек окружения."""

        if self.APP_ENV == "test":
            if (
                self.POSTGRES_DB != "test_db"
                or self.POSTGRES_HOST != "test_db"
            ):
                raise ValueError(
                    "Тестовое окружение должно использовать "
                    "только test_db на хосте test_db"
                )

        if self.APP_ENV == "prod":
            if (
                self.POSTGRES_DB == "test_db"
                or self.POSTGRES_HOST == "test_db"
            ):
                raise ValueError(
                    "Production не должен использовать тестовую БД"
                )

            if self.POSTGRES_PASSWORD.lower() in {
                "postgres", "password", "changeme"
            }:
                raise ValueError(
                    "Недопустимый пароль PostgreSQL для production"
                )

            if self.JWT_SECRET.lower().startswith("replace_with"):
                raise ValueError(
                    "Замените демонстрационный JWT_SECRET"
                )

        return self

    @property
    def DATABASE_URL(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )


@lru_cache
def get_settings() -> Settings:
    """Возвращает кешированный объект настроек."""
    return Settings()


# Совместимость с текущими модулями и тестами.
config = get_settings()