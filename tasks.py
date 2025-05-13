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

            # Удаляем из очереди
            await session.delete(item)
            await session.commit()

            # Уведомления
            user = await session.get(User, item.user_id)
            if user.notify_mode == "each":
                await bot.send_message(
                    chat_id=item.user_id,
                    text=f"Переход: {initial_url} → {final_url} ({state})",
                    reply_to_message_id=item.message_id
                )
            elif user.notify_mode == "summary":
                # если очередь пуста после удаления
                q = await session.execute(
                    select(Queue).filter_by(user_id=item.user_id)
                )
                if not q.scalars().all():
                    events = await session.execute(
                        select(Event).filter_by(user_id=item.user_id, state="success")
                    )
                    lines = [
                        f"{e.initial_url} → {e.final_url} в {e.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                        for e in events.scalars().all()
                    ]
                    await bot.send_message(
                        chat_id=item.user_id,
                        text="Сводка переходов:\n" + "\n".join(lines)
                    )

async def tick(context: CallbackContext):
    bot = context.bot
    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()
        result = await session.execute(
            select(Queue).filter(
                (Queue.transition_time <= now) | (Queue.transition_time.is_(None))
            )
        )
        items = result.scalars().all()
        for item in items:
            asyncio.create_task(process_queue_item(item, bot))

def setup_scheduler(app):
    """
    Настраивает встроенный JobQueue PTB:
      - tick каждую минуту, первый запуск сразу.
    Вызывать после register_handlers(app) и перед app.run_polling().
    """
    app.job_queue.run_repeating(tick, interval=60, first=0)
