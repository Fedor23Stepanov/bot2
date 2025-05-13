import json
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL, INITIAL_ADMIN
from models import Base, User, DeviceOption

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    # 1) Создать таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2) Загрузить devices.json в device_options, если пусто
    async with AsyncSessionLocal() as session:
        count = await session.scalar(DeviceOption.__table__.count())
        if count == 0:
            with open("devices.json") as f:
                data = json.load(f)
            for id_, device in data.items():
                session.add(DeviceOption(
                    id=int(id_),
                    ua=device["ua"],
                    css_size=device["css_size"],
                    platform=device["platform"],
                    dpr=device["dpr"],
                    mobile=device["mobile"],
                    model=device.get("model")
                ))
        # 3) Добавить initial admin в pending
        admin = await session.get(User, {"username": INITIAL_ADMIN})
        if not admin:
            session.add(User(
                username=INITIAL_ADMIN,
                role="admin",
                status="pending",
                invited_by=None
            ))
        await session.commit()
