# tasks.py

import asyncio
import random
import uuid
from datetime import datetime

from telegram.ext import CallbackContext
from sqlalchemy import select

from db import AsyncSessionLocal
from models import Queue, Event, DeviceOption, User, ProxyLog
from redirector import fetch_redirect, ProxyAcquireError

# Ограничивает одновременное выполнение fetch_redirect
semaphore = asyncio.Semaphore(1)

async def fetch_db_user(session, telegram_id: int):
    """Возвращает User по Telegram ID или None."""
    result = await session.execute(
        select(User).filter_by(user_id=telegram_id)
    )
    return result.scalar_one_or_none()

async def process_queue_item(item, bot):
    async with semaphore:
        async with AsyncSessionLocal() as session:
            # Выбираем случайное устройство
            result = await session.execute(select(DeviceOption.id))
            ids = result.scalars().all()
            chosen_id = random.choice(ids)
            device_obj = await session.get(DeviceOption, chosen_id)
            device = {
                "ua": device_obj.ua,
                "css_size": device_obj.css_size,
                "platform": device_obj.platform,
                "dpr": device_obj.dpr,
                "mobile": device_obj.mobile,
                "model": device_obj.model,
            }

            proxy_id = str(uuid.uuid4())
            initial_url = final_url = ip = isp = None
            attempts = []
            state = "redirector_error"

            try:
                (initial_url,
                 final_url,
                 ip,
                 isp,
                 _,
                 attempts) = await asyncio.to_thread(fetch_redirect, item.url, device)
                state = "success"
            except ProxyAcquireError as e:
                state = "proxy_error"
                attempts = e.attempts
            except Exception:
                state = "redirector_error"

            # Логируем proxy_attempts
            for a in attempts:
                session.add(ProxyLog(
                    id=proxy_id,
                    attempt=a["attempt"],
                    ip=a.get("ip"),
                    city=a.get("city"),
                ))

            # Сохраняем событие
            session.add(Event(
                user_id=item.user_id,
                device_option_id=(device_obj.id if state == "success" else None),
                state=state,
                proxy_id=proxy_id,
                initial_url=initial_url,
                final_url=final_url,
                ip=ip,
                isp=isp,
            ))

            # Помечаем задачу как выполненную
            item.status = "done"
            await session.commit()

            # Мгновенное уведомление
            db_user = await fetch_db_user(session, item.user_id)
            if db_user:
                await bot.send_message(
                    chat_id=item.user_id,
                    text=f"Переход: {initial_url} → {final_url} ({state})",
                    reply_to_message_id=item.message_id,
                    disable_web_page_preview=True
                )

async def tick(context: CallbackContext):
    bot = context.bot
    async with AsyncSessionLocal() as session:
        now = datetime.now()
        # В одной транзакции выбираем все pending задачи и сразу помечаем in_progress
        async with session.begin():
            result = await session.execute(
                select(Queue)
                  .where(Queue.status == "pending", Queue.transition_time <= now)
            )
            items = result.scalars().all()
            for item in items:
                item.status = "in_progress"
        # после выхода из session.begin() транзакция коммитится

    # Запускаем обработку вне транзакции
    for item in items:
        asyncio.create_task(process_queue_item(item, bot))

def setup_scheduler(app):
    """
    Настраивает JobQueue PTB:
      - tick каждую минуту, первый запуск сразу.
    """
    app.job_queue.run_repeating(tick, interval=60, first=0)
