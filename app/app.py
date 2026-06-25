"""Точка входа FastAPI-приложения.

Модуль создает экземпляр FastAPI, подключает lifespan-приложения и описывает
HTTP endpoint для регистрации, аутентификации, управления пользователями,
бронированиями и переговорными комнатами.
"""
from fastapi import FastAPI, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
import datetime

from .lifespan import lifespan
from .dependencies import get_db_session
from .auth import CurrentUserDep, AdminUserDep
from . import models, schemas, services


app = FastAPI(
    title='Booking service',
    description='Тестовое задание по бронированию конференц залов',
    lifespan=lifespan
)

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]

@app.post(
    '/register',
    response_model=schemas.GetUserResponse,
    description='Регистрирует нового пользователя. '
                'Первый пользователь в системе получает роль администратора.'
)
async def register(
        user_data: schemas.RegisterRequest,
        session: SessionDep
):
    return await services.register_user(session, user_data)

@app.post(
    '/login',
    response_model=schemas.LoginResponse,
    description='Проверяет логин и пароль пользователя и возвращает '
                'JWT-токен для доступа к защищенным endpoint.'
)
async def login(
        login_data: schemas.LoginRequest,
        session: SessionDep
):
    return await services.login_user(session, login_data)

@app.get(
    '/users/self',
    response_model=schemas.GetUserResponse,
    description='Возвращает профиль текущего авторизованного пользователя.'
)
async def get_self(
        current_user: CurrentUserDep
):
    return services.get_self(current_user)

@app.get(
    '/users',
    response_model=schemas.GetUsersResponse,
    description='Возвращает список всех пользователей. Доступно только администратору.'
)
async def get_users(
        _admin: AdminUserDep,
        session: SessionDep
):
    return await services.get_users(session)

@app.get(
    '/users/{user_id}',
    response_model=schemas.GetUserResponse,
    description='Возвращает пользователя по идентификатору. Доступно только администратору.'
)
async def get_user(
        user_id: int,
        _admin: AdminUserDep,
        session: SessionDep
):
    return await services.get_db_object_by_id(session, models.User, user_id)

@app.patch(
    '/users/{user_id}',
    response_model=schemas.GetUserResponse,
    description='Обновляет данные пользователя. Сотрудник может изменять '
                'только свой профиль, администратор — любого пользователя.'
)
async def update_user(
        user_id: int,
        current_user: CurrentUserDep,
        session: SessionDep,
        update_data: schemas.UpdateUserRequest
):
    return await services.update_user_by_id(session, user_id, update_data, current_user)

@app.post(
    '/bookings',
    response_model=schemas.GetBookingResponse,
    description='Создает бронирование переговорной комнаты на выбранную дату и временной слот.'
)
async def book_room(
        booking_data: schemas.CreateBookingRequest,
        current_user: CurrentUserDep,
        session: SessionDep
):
    return await services.book_room(session, current_user, booking_data)

@app.get(
    '/bookings/all',
    response_model=schemas.GetBookingsResponse,
    description='Возвращает все бронирования. Можно отфильтровать результат '
                'по query-параметру date. Доступно только администратору.'
)
async def get_all_bookings(
        _admin: AdminUserDep,
        session: SessionDep,
        date: datetime.date | None = None
):
    return await services.get_all_bookings(session, date)

@app.get(
    '/bookings/{booking_id}',
    response_model=schemas.GetBookingResponse,
    description='Возвращает бронирование по идентификатору. Сотрудник видит '
                'только свои бронирования, администратор — любые.'
)
async def book_room_info(
        booking_id: int,
        current_user: CurrentUserDep,
        session: SessionDep
):
    return await services.book_room_info(session, current_user, booking_id)

@app.get(
    '/bookings',
    response_model=schemas.GetBookingsResponse,
    description='Возвращает все бронирования текущего авторизованного пользователя.'
)
async def get_all_user_bookings(
        current_user: CurrentUserDep,
        session: SessionDep
):
    return await services.get_all_user_bookings(session, current_user)

@app.patch(
    '/bookings/cancel/{booking_id}',
    response_model=schemas.CancelResponse,
    description='Отменяет бронирование. Сотрудник может отменить только свое '
                'бронирование, администратор — любое.'
)
async def book_room_update(
        current_user: CurrentUserDep,
        session: SessionDep,
        booking_id: int
):
    return await services.book_room_cancel(session, current_user, booking_id)

@app.get(
    '/rooms/available/{date}',
    response_model=schemas.AvailableRoomsResponse,
    description='Возвращает доступные комнаты и свободные временные слоты на выбранную дату.'
)
async def get_date_available_bookings(
        date: datetime.date,
        _current_user: CurrentUserDep,
        session: SessionDep
):
    return await services.get_date_available_bookings(session, date)

@app.get(
    '/rooms',
    response_model=schemas.RoomsResponse,
    description='Возвращает список всех переговорных комнат. Требует авторизации.'
)
async def get_all_rooms_info(
        session: SessionDep,
        _current_user: CurrentUserDep,
):
    return await services.get_all_rooms_info(session)

@app.get(
    '/rooms/{room_id}',
    response_model=schemas.RoomResponse,
    description='Возвращает переговорную комнату по идентификатору. Требует авторизации.'
)
async def get_room_info_by_id(
        session: SessionDep,
        _current_user: CurrentUserDep,
        room_id: int
):
    return await services.get_db_object_by_id(session, models.Room, room_id)