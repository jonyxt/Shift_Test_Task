"""Сервисный слой приложения.

Модуль содержит бизнес-логику бронирования переговорных комнат:
регистрацию и авторизацию пользователей, управление пользователями,
создание и отмену бронирований, получение списка комнат и проверку
доступности временных слотов.

Функции сервисного слоя вызываются из endpoint и работают с базой данных
через асинхронную SQLAlchemy-сессию.
"""
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select, func, and_
from typing import TypeVar
import datetime

from . import models, schemas, auth


ModelType = TypeVar('ModelType')

async def commit_refresh_db(model: ModelType, error: str, session: AsyncSession) -> ModelType:
    """Сохраняет изменения в базе данных и обновляет ORM-объект.

    Выполняет commit текущей транзакции, затем refresh переданного объекта,
    чтобы получить актуальные значения из базы данных после сохранения.
    """
    try:
        await session.commit()
        await session.refresh(model)
        return model
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{error}"
        )

async def initial_rooms_and_time_windows(session: AsyncSession) -> None:
    """Создает стартовые комнаты и временные слоты, если они отсутствуют.

    Функция используется при запуске приложения. Она проверяет наличие записей
    в таблицах комнат и временных слотов и добавляет базовый набор данных только
    в пустые таблицы, чтобы не дублировать записи при повторном старте.
    """
    rooms_count_query = select(func.count()).select_from(models.Room)
    rooms_count = await session.scalar(rooms_count_query)
    if rooms_count > 0:
        return
    rooms = {
        'Большой конференц зал': 'До 25 человек',
        'Средний конференц зал': 'До 15 человек',
        'Малый конференц зал': 'До 8 человек'
    }
    for room_name, room_description in rooms.items():
        new_room = models.Room(
            room_name=room_name,
            description=room_description
        )
        session.add(new_room)
        await session.flush()
        time_windows = [
            models.TimeWindow(
                room_id=new_room.id,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(12, 0)
            ),
            models.TimeWindow(
                room_id=new_room.id,
                start_time=datetime.time(13, 0),
                end_time=datetime.time(16, 0)
            ),
            models.TimeWindow(
                room_id=new_room.id,
                start_time=datetime.time(16, 0),
                end_time=datetime.time(19, 0)
            )
        ]
        session.add_all(time_windows)
    await session.commit()

async def register_user(
        session: AsyncSession,
        user_data: schemas.RegisterRequest
) -> models.User:
    """Регистрирует нового пользователя с ролью employee.

    Пароль сохраняется в базе данных только в виде хеша.
    """
    new_user = models.User(
        username=user_data.username,
        hashed_password=auth.hash_password(user_data.password),
        email=user_data.email,
        phone=user_data.phone,
        role=models.UserRole.EMPLOYEE
    )
    session.add(new_user)
    return await commit_refresh_db(
        model=new_user,
        error='Пользователь с таким именем/почтой/телефоном уже существует',
        session=session
    )

async def login_user(
        session: AsyncSession,
        login_data: schemas.LoginRequest
) -> schemas.LoginResponse:
    """Аутентифицирует пользователя и возвращает JWT-токен.

    Ищет пользователя по username, проверяет переданный пароль с сохраненным
    хешем и при успешной проверке создает access token для дальнейших запросов
    к защищенным endpoint.
    """
    query = select(models.User).where(models.User.username == login_data.username)
    user = await session.scalar(query)
    if user is None:
        raise HTTPException(status_code=401, detail='Неверный логин или пароль')
    if not auth.check_password(login_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail='Неверный логин или пароль')
    token = auth.create_access_token(user_id=user.id)
    return schemas.LoginResponse(access_token=token)

def get_self(current_user: models.User) -> models.User:
    """Возвращает данные текущего авторизованного пользователя."""
    return current_user

async def get_users(session: AsyncSession) -> dict:
    """Возвращает список всех пользователей.

    Функция предназначена для административного сценария, когда нужно получить
    полный список пользователей системы.
    """
    query = select(models.User)
    result = await session.execute(query)
    users = result.scalars().unique().all()
    return {
        'users': users
    }

async def get_db_object_by_id(
        session: AsyncSession,
        orm_model: type[ModelType],
        db_object_id: int
) -> ModelType:
    """Получает ORM-объект по идентификатору.

    Ищет объект указанной модели по primary key. Если запись не найдена,
    выбрасывает HTTP-ошибку 404 с переданным сообщением.
    """
    query = select(orm_model).where(orm_model.id == db_object_id)
    result = await session.execute(query)
    db_object = result.scalar_one_or_none()
    if db_object is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{orm_model.__name__} с id {db_object_id} не найден"
        )
    return db_object

async def update_user_by_id(
        session: AsyncSession,
        user_id: int,
        update_data: schemas.UpdateUserRequest,
        current_user: models.User
) -> models.User:
    """Обновляет данные пользователя.

    Обычный пользователь может изменять только свои данные. Администратор может
    изменять данные любого пользователя.

    При изменении роли проверяется, что в системе не останется ни одного
    администратора, чтобы нельзя было удалить последнего администратора из системы.
    Поля, которые не были переданы в запросе, не изменяются.
    """
    user = await get_db_object_by_id(session, models.User, user_id)
    if current_user.role == models.UserRole.EMPLOYEE:
        if current_user.id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Сотрудники могут менять только свой профиль'
            )
        if 'role' in update_data.model_fields_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Только Администраторы могут менять роли пользователей'
            )
    update_dict = update_data.model_dump(exclude_unset=True)
    for field in ('username', 'email', 'role'):
        if field in update_dict and update_dict[field] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{field} не может быть null"
            )
    if (update_dict.get('role') == models.UserRole.EMPLOYEE
        and user.role == models.UserRole.ADMIN):
        admins_count_query = select(func.count()).select_from(models.User).where(
            models.User.role == models.UserRole.ADMIN
        )
        admins_count = await session.scalar(admins_count_query)
        if admins_count == 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Нельзя снять роль у последнего администратора'
            )
    for key, value in update_dict.items():
        setattr(user, key, value)
    return await commit_refresh_db(
        model=user,
        error='Пользователь с таким именем/почтой/телефоном уже существует',
        session=session
    )

async def book_room(
        session: AsyncSession,
        current_user: models.User,
        booking_data: schemas.CreateBookingRequest
) -> models.Booking:
    """Создает бронирование комнаты на выбранную дату и временной слот.

    Проверяет существование комнаты и временного слота, запрещает бронирование
    на прошедшие даты и не позволяет создать активное бронирование, если этот
    слот уже занят другим активным бронированием.
    """
    if booking_data.date < datetime.date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Нельзя создать бронирование на прошедшую дату'
        )
    query = (
        select(models.TimeWindow)
        .join(models.Room, models.Room.id == models.TimeWindow.room_id)
        .where(
            models.TimeWindow.id == booking_data.time_window_id,
            models.TimeWindow.room_id == booking_data.room_id,
            models.Room.is_active.is_(True)
        )
    )
    time_window = await session.scalar(query)
    if time_window is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Комната не существует, неактивна или слот не принадлежит выбранной комнате'
        )
    new_booking = models.Booking(
        owner_id=current_user.id,
        room_id=booking_data.room_id,
        date=booking_data.date,
        time_window_id=booking_data.time_window_id
    )
    session.add(new_booking)
    return await commit_refresh_db(
        model=new_booking,
        error='Такая бронь уже существует',
        session=session
    )

async def book_room_info(
        session: AsyncSession,
        current_user: models.User,
        booking_id: int
) -> models.Booking:
    """Возвращает подробную информацию о бронировании.

    Обычный пользователь может получить только свое бронирование. Администратор
    может получить информацию о любом бронировании.
    """
    booking = await get_db_object_by_id(session, models.Booking, booking_id)
    if current_user.role == models.UserRole.EMPLOYEE:
        if current_user.id != booking.owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Недостаточно прав для просмотра брони'
            )
    return booking

async def get_all_bookings(
        session: AsyncSession,
        date: datetime.date | None = None
) -> dict:
    """Возвращает список всех бронирований.

    Если передана дата, возвращает бронирования только за эту дату. Функция
    используется для административного просмотра бронирований.
    """
    query = (
        select(models.Booking)
        .options(
            selectinload(models.Booking.owner),
            selectinload(models.Booking.room),
            selectinload(models.Booking.time_window),
            selectinload(models.Booking.cancelled_by),
        )
    )
    if date is not None:
        query = query.where(models.Booking.date == date)
    result = await session.execute(query)
    bookings = result.scalars().unique().all()
    return {
        'bookings': bookings
    }

async def get_all_user_bookings(
        session: AsyncSession,
        current_user: models.User,
) -> dict:
    """Возвращает все бронирования текущего пользователя."""
    query = (
        select(models.Booking)
        .where(models.Booking.owner_id == current_user.id)
        .options(
            selectinload(models.Booking.owner),
            selectinload(models.Booking.room),
            selectinload(models.Booking.time_window),
            selectinload(models.Booking.cancelled_by),
        )
    )
    result = await session.execute(query)
    bookings = result.scalars().unique().all()
    return {
        'bookings': bookings
    }

async def book_room_cancel(
        session: AsyncSession,
        current_user: models.User,
        booking_id: int
) -> dict:
    """Отменяет бронирование.

    Обычный пользователь может отменить только свое бронирование. Администратор
    может отменить любое бронирование. Отмена выполняется через изменение флага
    is_active, без удаления записи из базы данных.
    """
    booking = await get_db_object_by_id(session, models.Booking, booking_id)
    if current_user.role == models.UserRole.EMPLOYEE:
        if current_user.id != booking.owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail='Сотрудники могут отменять только свои бронирования'
            )
    if booking.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Данное бронирование уже было отменено'
        )
    booking.is_active = False
    booking.cancelled_at = datetime.datetime.now(datetime.UTC)
    booking.cancelled_by_id = current_user.id
    await session.commit()
    await session.refresh(booking)
    return {
        'status': 'Бронирование отменено'
    }

async def get_date_available_bookings(
        session: AsyncSession,
        date: datetime.date
) -> dict:
    """Возвращает доступные комнаты и временные слоты на выбранную дату.

    Для каждой комнаты определяет временные слоты, которые не заняты активными
    бронированиями на указанную дату.
    """
    query = (
        select(models.Booking.id)
        .where(
            and_(
                models.Booking.room_id == models.Room.id,
                models.Booking.time_window_id == models.TimeWindow.id,
                models.Booking.date == date,
                models.Booking.is_active.is_(True)
            )
        )
        .exists()
    )
    result = await session.execute(
        select(models.Room, models.TimeWindow)
        .join(models.TimeWindow, models.TimeWindow.room_id == models.Room.id)
        .where(
            models.Room.is_active.is_(True),
            ~query
        )
        .order_by(models.Room.id, models.TimeWindow.start_time)
    )
    rows = result.all()
    rooms = {}
    for room, window in rows:
        if room.id not in rooms:
            rooms[room.id] = {
                'id': room.id,
                'room_name': room.room_name,
                'description': room.description,
                'available_time_windows': [],
            }
        rooms[room.id]['available_time_windows'].append({
            'id': window.id,
            'start_time': window.start_time,
            'end_time': window.end_time
        })
    return {
        'rooms': list(rooms.values())
    }

async def get_all_rooms_info(session: AsyncSession) -> dict:
    """Возвращает список всех переговорных комнат."""
    query = select(models.Room)
    result = await session.execute(query)
    rooms = result.scalars().unique().all()
    return {
        'rooms': rooms
    }