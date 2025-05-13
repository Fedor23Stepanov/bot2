import asyncio
import uuid
import random
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from db import AsyncSessionLocal
from models import User, Queue, Event, DeviceOption, ProxyLog
from redirector import fetch_redirect, ProxyAcquireError

# Ограничение параллельных редиректов
semaphore = asyncio.Semaphore(1)

async def process_queue_item(item, bot):
    """
    Обрабатывает одну запись из очереди: выполняет переход через редиректор,
    логирует proxy attempts и событие, уведомляет пользователя.
    """
    session = AsyncSessionLocal()
    try:
        # Выбираем случайное устройство
        res = await session.execute(select(DeviceOption.id))
        ids = res.scalars().all()
        device_obj = await session.get(DeviceOption, random.choice(ids))
        device = {
            "ua": device_obj.ua,
            "css_size": device_obj.css_size,
            "platform": device_obj.platform,
            "dpr": device_obj.dpr,
            "mobile": device_obj.mobile,
            "model": device_obj.model,
            "id": device_obj.id
        }

        proxy_id = str(uuid.uuid4())
        # Выполняем переход через редиректор, в ограниченном семафором контексте
        async with semaphore:
            initial_url, final_url, ip, isp, _, attempts = await asyncio.to_thread(
                fetch_redirect, item.url, device
            )
        state = "success"
        # Логируем данные попыток proxy
        for a in attempts:
            session.add(ProxyLog(
                id=proxy_id,
                attempt=a["attempt"],
                ip=a["ip"],
                city=a["city"]
            ))
    except ProxyAcquireError as e:
        state = "proxy_error"
        proxy_id = str(uuid.uuid4())
        attempts = e.attempts
        for a in attempts:
            session.add(ProxyLog(
                id=proxy_id,
                attempt=a["attempt"],
                ip=a.get("ip"),
                city=a.get("city")
            ))
        initial_url = None
        final_url = None
        ip = None
        isp = None
    except Exception:
        state = "redirector_error"
        initial_url = None
        final_url = None
        ip = None
        isp = None
        proxy_id = None

    # Сохраняем событие
    session.add(Event(
        user_id=item.user_id,
        device_option_id=device_obj.id if state=="success" else None,
        state=state,
        proxy_id=proxy_id,
        initial_url=initial_url,
        final_url=final_url,
        ip=ip,
        isp=isp,
    ))
    # Удаляем задачу из очереди
    session.delete(item)
    await session.commit()

    # Уведомления пользователю
    db_user = await session.get(User, item.user_id)
    if db_user.notify_mode == "each":
        await bot.send_message(
            chat_id=item.user_id,
            text=(f"Переход по ссылке {item.url} выполнен. "
                  f"Статус: {state}\n"
                  f"Конечный URL: {final_url or state}")
        )
    elif db_user.notify_mode == "summary":
        # если больше нет задач в очереди — отправляем сводку
        res = await session.execute(select(Queue).filter_by(user_id=item.user_id))
        remaining = res.scalars().all()
        if not remaining:
            # собираем все события пользователя
            res_ev = await session.execute(select(Event).filter_by(user_id=item.user_id))
            events = res_ev.scalars().all()
            texts = [
                f"{e.initial_url} -> {e.final_url or e.state} at {e.timestamp}" 
                for e in events
            ]
            summary = "\n".join(texts)
            await bot.send_message(
                chat_id=item.user_id,
                text=("Ваша очередь завершена. История:\n" + summary)
            )
    session.close()

async def tick(bot):
    session = AsyncSessionLocal()
    now = datetime.utcnow()
    res = await session.execute(
        select(Queue).where(
            (Queue.transition_time <= now) | (Queue.transition_time.is_(None))
        )
    )
    items = res.scalars().all()
    for item in items:
        # создаём задачу для обработки
        asyncio.create_task(process_queue_item(item, bot))
    session.close()

async def start_scheduler(app):
    scheduler = AsyncIOScheduler()
    # Запускать tick каждую минуту
    scheduler.add_job(lambda: asyncio.create_task(tick(app.bot)), 'interval', seconds=60)
    scheduler.start()
