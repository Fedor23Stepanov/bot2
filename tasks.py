import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
from db import AsyncSessionLocal
from models import Queue, ProxyLog, Event, DeviceOption
from redirector import fetch_redirect
import uuid, random

semaphore = asyncio.Semaphore(1)

async def process_queue_item(item, bot):
    async with semaphore:
        session = AsyncSessionLocal()
        proxy_id = str(uuid.uuid4())
        device = await session.get(DeviceOption, random.choice([...])).__dict__
        try:
            initial, final, ip, isp, device, attempts = await asyncio.to_thread(
                fetch_redirect, item.url, device
            )
            # логируем прокси_attempts
            for a in attempts:
                session.add(ProxyLog(id=proxy_id, attempt=a["attempt"], ip=a["ip"], city=a["city"]))
            state = "success"
        except Exception as e:
            state = "proxy_error" if isinstance(e, ProxyAcquireError) else "redirector_error"
        # сохраняем Event
        session.add(Event(
            user_id=item.user_id,
            device_option_id=device["id"],
            state=state,
            proxy_id=proxy_id,
            initial_url=initial if state=="success" else None,
            final_url=final if state=="success" else None,
            ip=ip if state=="success" else None,
            isp=isp if state=="success" else None
        ))
        # уведомления
        # ... (each vs summary)
        await session.delete(item)
        await session.commit()
        await session.close()

async def tick(bot):
    session = AsyncSessionLocal()
    now = datetime.utcnow()
    items = await session.execute(
        select(Queue).where(
            (Queue.transition_time<=now) | (Queue.transition_time.is_(None))
        )
    )
    for item in items.scalars():
        asyncio.create_task(process_queue_item(item, bot))
    await session.close()

async def start_scheduler(app):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: asyncio.create_task(tick(app.bot)), "interval", seconds=60)
    scheduler.start()
