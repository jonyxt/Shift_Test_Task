import asyncio
import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from . import models
from .database import AsyncSessionLocal, engine


INITIAL_ROOMS = {
    "Большой конференц зал": "До 25 человек",
    "Средний конференц зал": "До 15 человек",
    "Малый конференц зал": "До 8 человек",
}

INITIAL_SLOTS = (
    (datetime.time(9, 0), datetime.time(12, 0)),
    (datetime.time(13, 0), datetime.time(16, 0)),
    (datetime.time(16, 0), datetime.time(19, 0)),
)


async def seed_initial_data(session: AsyncSession) -> None:
    """Создаёт недостающие комнаты и слоты без дубликатов."""

    async with session.begin():
        # Защита от одновременного запуска двух seed-команд.
        await session.execute(
            text("SELECT pg_advisory_xact_lock(812741098)")
        )

        for name, description in INITIAL_ROOMS.items():
            room = await session.scalar(
                select(models.Room)
                .where(models.Room.room_name == name)
                .order_by(models.Room.id)
                .limit(1)
            )

            if room is None:
                room = models.Room(
                    room_name=name,
                    description=description,
                )
                session.add(room)
                await session.flush()

            for start_time, end_time in INITIAL_SLOTS:
                existing_slot = await session.scalar(
                    select(models.TimeWindow.id)
                    .where(
                        models.TimeWindow.room_id == room.id,
                        models.TimeWindow.start_time == start_time,
                        models.TimeWindow.end_time == end_time,
                    )
                    .limit(1)
                )

                if existing_slot is None:
                    session.add(
                        models.TimeWindow(
                            room_id=room.id,
                            start_time=start_time,
                            end_time=end_time,
                        )
                    )


async def main() -> None:
    """CLI-точка входа для инициализации данных."""

    try:
        async with AsyncSessionLocal() as session:
            await seed_initial_data(session)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
