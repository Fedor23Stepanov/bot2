# handlers.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters, CommandHandler
import re
from datetime import datetime, timedelta
import random
from db import AsyncSessionLocal
from models import User, Queue, Event
from keyboards import (
    main_menu, queue_menu, notifications_menu,
    transition_mode_menu, users_menu, add_user_menu,
    add_moderator_menu
)

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = AsyncSessionLocal()
    # Проверка пользователя
    db_user = await session.get(User, user.id)
    if not db_user:
        # проверка по username в pending
        db_user = await session.execute(
            session.query(User).filter_by(username=user.username, status='pending')
        )
        db_user = db_user.scalar()
        if db_user:
            # активировать
            db_user.user_id = user.id
            db_user.activated_date = datetime.utcnow()
            db_user.status = 'activ'
            await session.commit()
        else:
            await session.close()
            return  # игнорируем

    # Извлечение ссылок
    text = update.message.text or ''
    links = re.findall(r"https?://\S+|t\.me/\S+|@\w+|\b\w+\.\w+\b", text)
    if len(links) == 0:
        await update.message.reply_text("в сообщение нет ссылок")
        await session.add(Event(user_id=user.id, state='no_link', timestamp=datetime.utcnow()))
        await session.commit()
        await session.close()
        return
    if len(links) > 1:
        await update.message.reply_text("пришлите одну ссылку за раз")
        await session.add(Event(user_id=user.id, state='many_links', timestamp=datetime.utcnow()))
        await session.commit()
        await session.close()
        return
    # Одна ссылка
    url = links[0]
    # расчет времени
    if db_user.transition_mode == 'immediate':
        transition_time = None
    else:
        now = datetime.utcnow()
        end_of_day = now.replace(hour=23, minute=59, second=59)
        if (end_of_day - now) < timedelta(hours=2):
            # завтра случайное время
            tomorrow = now + timedelta(days=1)
            start = tomorrow.replace(hour=0, minute=0)
            end = tomorrow.replace(hour=23, minute=59)
        else:
            start, end = now, end_of_day
n        rand_ts = start + (end - start) * random.random()
        transition_time = rand_ts
    # добавить в очередь
    queue_item = Queue(
        user_id=user.id,
        message_id=update.message.message_id,
        url=url,
        transition_time=transition_time
    )
    session.add(queue_item)
    await session.commit()
    await session.close()
    await update.message.reply_text("Ссылка добавлена в очередь.")

async def on_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = AsyncSessionLocal()
    items = await session.execute(
        session.query(Queue).filter_by(user_id=user.id)
    )
    items = items.scalars().all()
    kb = queue_menu(items)
    await update.effective_message.reply_text("Ваша очередь:", reply_markup=kb)
    await session.close()

async def on_delete_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, item_id = query.data.split(':')
    session = AsyncSessionLocal()
    item = await session.get(Queue, int(item_id))
    if item:
        await session.delete(item)
        await session.commit()
    await session.answer()
    await on_queue(update, context)
    await session.close()

# ... остальные обработчики: statistics, history, notifications, transition_mode,
# users management, add_user, add_moderator и т.д.


def register_handlers(app):
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(CommandHandler('queue', on_queue))
    app.add_handler(CallbackQueryHandler(on_delete_queue, pattern=r'^del_queue:'))
    # TODO: регистрировать остальные CallbackQueryHandler'ы по шаблонам
