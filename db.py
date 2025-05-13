#db.py

import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func
from config import DATABASE_URL, INITIAL_ADMIN
from models import Base, User, DeviceOption

# Создаём асинхронный движок и сессию
engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def init_db():
    """
    Инициализация БД:
    1) Создаёт таблицы по всем моделям.
    2) Загружает device_options из devices.json, если таблица пуста.
    3) Добавляет initial admin в users со статусом pending, если нет.
    """
    # 1) Создать таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2) Наполнить device_options и добавить админа
    async with AsyncSessionLocal() as session:
        # Проверяем, пуста ли таблица device_options
        count = await session.scalar(
            select(func.count()).select_from(DeviceOption)
        )
        if count == 0:
            with open("devices.json", encoding="utf-8") as f:
                data = json.load(f)
            for id_str, device in data.items():
                session.add(DeviceOption(
                    id=int(id_str),
                    ua=device["ua"],
                    css_size=device["css_size"],
                    platform=device["platform"],
                    dpr=device["dpr"],
                    mobile=device["mobile"],
                    model=device.get("model")
                ))

        # Проверяем наличие initial admin по username
        result = await session.execute(
            select(User).filter_by(username=INITIAL_ADMIN)
        )
        admin = result.scalar_one_or_none()
        if not admin:
            session.add(User(
                username=INITIAL_ADMIN,
                role="admin",
                status="pending",
                invited_by=None
            ))

        await session.commit()
