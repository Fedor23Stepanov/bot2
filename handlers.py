# handlers.py

import re
import random
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from sqlalchemy import select

from db import AsyncSessionLocal
from models import User, Queue, Event
from keyboards import main_menu, queue_menu

# /start handler
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Меню',
        reply_markup=main_menu(update.effective_user.role)
    )

# Callback: prompt to add a new user
async def add_user_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Для добавления нового пользователя пришлите его ник"
    )
    context.user_data['adding_role'] = 'user'
    context.user_data['inviter_id'] = update.effective_user.id

# Callback: prompt to add a new moderator
async def add_moderator_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Для добавления нового модератора пришлите его ник"
    )
    context.user_data['adding_role'] = 'moderator'
    context.user_data['inviter_id'] = update.effective_user.id

# Message handler: links and new-user flow
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ''

    # --- New-user/moderator flow ---
    role_to_add = context.user_data.get('adding_role')
    inviter_id = context.user_data.get('inviter_id')
    if role_to_add:
        nick = text.strip()
        normalized = re.sub(r'^(?:https?://t\.me/|t\.me/|@)', '', nick)
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(User).filter_by(username=normalized)
            )
            exists = res.scalar_one_or_none()
            if not exists:
                new_user = User(
                    username=normalized,
                    role=role_to_add,
                    status='pending',
                    invited_by=inviter_id
                )
                session.add(new_user)
                await session.commit()
                role_name = 'Модератор' if role_to_add == 'moderator' else 'Пользователь'
                await update.message.reply_text(f"{role_name} @{normalized} успешно добавлен.")
            else:
                await update.message.reply_text(f"Пользователь @{normalized} уже существует.")
        context.user_data.pop('adding_role', None)
        context.user_data.pop('inviter_id', None)
        return

    # --- Regular-link processing ---
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        if not db_user:
            res = await session.execute(
                select(User).filter_by(username=user.username, status='pending')
            )
            pending_user = res.scalar_one_or_none()
            if pending_user:
                pending_user.user_id = user.id
                pending_user.status = 'activ'
                pending_user.activated_date = datetime.utcnow()
                await session.commit()
                db_user = pending_user
            else:
                return  # ignore all other users

        # extract links
        links = re.findall(r'https?://\S+|t\.me/\S+|@\w+', text)
        if not links:
            session.add(Event(user_id=user.id, state='no_link'))
            await session.commit()
            await update.message.reply_text("в сообщение нет ссылок")
            return
        if len(links) > 1:
            session.add(Event(user_id=user.id, state='many_links'))
            await session.commit()
            await update.message.reply_text("пришлите одну ссылку за раз")
            return

        url = links[0]
        # compute transition_time
        if db_user.transition_mode == 'immediate':
            transition_time = None
        else:
            now = datetime.utcnow()
            end_of_day = now.replace(hour=23, minute=59, second=59)
            if (end_of_day - now) < timedelta(hours=2):
                tomorrow = now + timedelta(days=1)
                start = tomorrow.replace(hour=0, minute=0, second=0)
                end = tomorrow.replace(hour=23, minute=59, second=59)
            else:
                start = now
                end = end_of_day
            transition_time = start + (end - start) * random.random()

        # add to queue
        queue_item = Queue(
            user_id=user.id,
            message_id=update.message.message_id,
            url=url,
            transition_time=transition_time
        )
        session.add(queue_item)
        await session.commit()
        await update.message.reply_text("Ссылка добавлена в очередь.")

# /queue handler
async def on_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Queue).filter_by(user_id=user.id)
        )
        items = res.scalars().all()
    kb = queue_menu(items)
    await update.effective_message.reply_text("Ваша очередь:", reply_markup=kb)

# Callback to delete an item from the queue
async def on_delete_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, item_id = query.data.split(':')
    async with AsyncSessionLocal() as session:
        item = await session.get(Queue, int(item_id))
        if item:
            await session.delete(item)
            await session.commit()
    # refresh queue list
    await on_queue(update, context)

def register_handlers(app):
    app.add_handler(CommandHandler('start', start_cmd))
    app.add_handler(CallbackQueryHandler(add_user_prompt, pattern=r'^add_user$'))
    app.add_handler(CallbackQueryHandler(add_moderator_prompt, pattern=r'^add_moderator$'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(CommandHandler('queue', on_queue))
    app.add_handler(CallbackQueryHandler(on_delete_queue, pattern=r'^del_queue:'))
