"""Pydantic-схемы запросов и ответов API.

Модуль описывает структуры данных, которые FastAPI использует для валидации
входящих запросов и сериализации ответов. Схемы отделяют публичный API-контракт
от внутренних SQLAlchemy-моделей.
"""
import datetime

from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator
from .models import UserRole


class RegisterRequest(BaseModel):
    """Данные для регистрации нового пользователя."""
    username: str = Field(min_length=4, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=12)

    @field_validator('password')
    @classmethod
    def validate_password_bytes(cls, value: str) -> str:
        if len(value.encode('utf=8')) > 72:
            raise ValueError(
                'Пароль не должен превышать 72 байта UTF-8'
            )
        return value

class LoginRequest(BaseModel):
    """Данные для получения JWT-токена."""
    username: str
    password: str

class LoginResponse(BaseModel):
    """Ответ с JWT-токеном после успешной аутентификации."""
    access_token: str
    token_type: str = 'bearer'

class GetUserResponse(BaseModel):
    """Публичное представление пользователя в ответах API."""
    id: int
    username: str
    email: EmailStr
    phone: str | None = None
    role: UserRole

    model_config = ConfigDict(from_attributes=True)

class GetUsersResponse(BaseModel):
    """Список пользователей для административных endpoint."""
    users: list[GetUserResponse]

class UpdateUserRequest(BaseModel):
    """Данные для частичного обновления пользователя."""
    username: str | None = Field(default=None, min_length=4, max_length=50)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=12)
    role: UserRole | None = None

class CreateBookingRequest(BaseModel):
    """Данные для создания бронирования."""
    room_id: int
    time_window_id: int
    date: datetime.date

class UserShortResponse(BaseModel):
    """Краткое представление пользователя во вложенных ответах."""
    id: int
    username: str

    model_config = ConfigDict(from_attributes=True)

class TimeWindowResponse(BaseModel):
    """Представление временного слота бронирования."""
    id: int
    start_time: datetime.time
    end_time: datetime.time

    model_config = ConfigDict(from_attributes=True)

class RoomShortResponse(BaseModel):
    """Краткое представление комнаты во вложенных ответах."""
    id: int
    room_name: str

    model_config = ConfigDict(from_attributes=True)

class GetBookingResponse(BaseModel):
    """Подробное представление бронирования."""
    id: int
    owner: UserShortResponse
    date: datetime.date
    room: RoomShortResponse
    time_window: TimeWindowResponse
    is_active: bool
    created_at: datetime.datetime
    cancelled_at: datetime.datetime | None = None
    cancelled_by: UserShortResponse | None = None

    model_config = ConfigDict(from_attributes=True)

class GetBookingsResponse(BaseModel):
    """Список бронирований."""
    bookings: list[GetBookingResponse]

class AvailableTimeWindowResponse(BaseModel):
    """Свободный временной слот для выбранной даты."""
    id: int
    start_time: datetime.time
    end_time: datetime.time

    model_config = ConfigDict(from_attributes=True)

class AvailableRoomResponse(BaseModel):
    """Комната со списком свободных временных слотов."""
    id: int
    room_name: str
    description: str | None = None
    available_time_windows: list[AvailableTimeWindowResponse]

    model_config = ConfigDict(from_attributes=True)

class AvailableRoomsResponse(BaseModel):
    """Список комнат с доступными слотами на дату."""
    rooms: list[AvailableRoomResponse]

class RoomResponse(BaseModel):
    """Подробное представление комнаты."""
    id: int
    room_name: str
    description: str | None = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class RoomsResponse(BaseModel):
    """Список переговорных комнат."""
    rooms: list[RoomResponse]

class CancelResponse(BaseModel):
    """Ответ после успешной отмены бронирования."""
    status: str = 'Бронирование отменено'