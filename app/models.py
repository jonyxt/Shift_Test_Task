"""ORM-модели приложения.

Модуль описывает таблицы пользователей, переговорных комнат, временных слотов
и бронирований. Модели используются SQLAlchemy для создания схемы базы данных
и выполнения запросов к PostgreSQL.
"""
import datetime

from enum import Enum
from .database import Base
from sqlalchemy import (
    String,
    ForeignKey,
    Boolean,
    CheckConstraint,
    UniqueConstraint,
    DateTime,
    Date,
    Time,
    Enum as SQLEnum,
    Index,
    text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class UserRole(str, Enum):
    """Роли пользователей в системе.

    EMPLOYEE — обычный сотрудник, который может работать только со своими
    бронированиями.
    ADMIN — администратор с доступом к пользователям и всем
    бронированиям.
    """
    EMPLOYEE = 'employee'
    ADMIN = 'admin'

class User(Base):
    """Пользователь системы бронирования.

    Пользователь может быть сотрудником или администратором. Имя пользователя,
    email и телефон должны быть уникальными, а пароль хранится только в виде
    хеша.
    """
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    phone: Mapped[str] = mapped_column(String(12), unique=True, nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SQLEnum(
            UserRole,
            name='user_role',
            values_callable=lambda enum_class: [member.value for member in enum_class]
        ),
        nullable=False,
        default=UserRole.EMPLOYEE
    )


class Room(Base):
    """Переговорная комната.

    Комната содержит название, описание и флаг активности. Неактивные комнаты
    не должны быть доступны для создания новых бронирований.
    """
    __tablename__ = 'rooms'

    id: Mapped[int] = mapped_column(primary_key=True)
    room_name: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(150), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TimeWindow(Base):
    """Временной слот бронирования комнаты.

    Слот принадлежит конкретной комнате и задает интервал времени. Для одной
    комнаты не может быть двух одинаковых интервалов, а начало слота должно
    быть раньше окончания.
    """
    __tablename__ = 'time_windows'

    __table_args__ = (
        UniqueConstraint(
            'room_id',
            'start_time',
            'end_time',
            name='unique_room_start_end_time_window'
        ),
        CheckConstraint(
            'start_time < end_time',
            name='check_start_time_before_end_time'
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey('rooms.id'), nullable=False)
    room: Mapped[Room] = relationship(Room, lazy='joined')
    start_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)


class Booking(Base):
    """Бронирование переговорной комнаты.

    Бронирование связывает пользователя, комнату, дату и временной слот.
    Активные бронирования защищены частичным уникальным индексом: для одной
    комнаты, даты и временного слота может существовать только одна активная
    бронь. После отмены бронь остается в истории, но перестает блокировать слот.
    """
    __tablename__ = 'bookings'

    __table_args__ = (
        Index(
            'unique_active_booking_room_date_time_window',
            'room_id',
            'date',
            'time_window_id',
            unique=True,
            postgresql_where=text('is_active = true')
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)
    owner: Mapped[User] = relationship(
        User,
        foreign_keys=[owner_id],
        lazy='joined'
    )
    room_id: Mapped[int] = mapped_column(ForeignKey('rooms.id'), nullable=False)
    room: Mapped[Room] = relationship(Room, lazy='joined')
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    time_window_id: Mapped[int] = mapped_column(ForeignKey('time_windows.id'), nullable=False)
    time_window: Mapped[TimeWindow] = relationship(TimeWindow, lazy='joined')
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    cancelled_at:  Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    cancelled_by: Mapped[User | None] = relationship(
        User,
        foreign_keys=[cancelled_by_id],
        lazy='joined'
    )