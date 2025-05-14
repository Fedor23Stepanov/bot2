# handlers.py

import re
import random
from datetime import datetime, timedelta

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)
from sqlalchemy import select, func

from db import AsyncSessionLocal
from models import User, Queue, Event
from keyboards import (
    main_menu,
    queue_menu,
    notifications_menu,
    transition_mode_menu,
    settings_menu,
    users_menu,
    add_user_menu,
    add_moderator_menu
)

# «Красная» клавиатура с кнопкой «Меню»
RED_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("Меню")]],
    resize_keyboard=True
)

async def fetch_db_user(session, telegram_id: int):
    """Возвращает User по Telegram ID или None."""
    result = await session.execute(
        select(User).filter_by(user_id=telegram_id)
    )
    return result.scalar_one_or_none()

# /start
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Автоматическая активация pending-пользователя при первом /start
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(User).filter_by(username=update.effective_user.username, status="pending")
        )
        pending = res.scalar_one_or_none()
        if pending and pending.user_id is None:
            pending.user_id = update.effective_user.id
            pending.status = "activ"
            pending.activated_date = datetime.utcnow()
            await session.commit()
    await update.message.reply_text(
        "Меню",
        reply_markup=RED_KEYBOARD
    )

# Текстовая «Меню» → inline-меню
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # При нажатии «Меню» также активируем пользователя, если он был pending
    async with AsyncSessionLocal() as session:
        # активация по username
        res = await session.execute(
            select(User).filter_by(username=update.effective_user.username, status="pending")
        )
        pending = res.scalar_one_or_none()
        if pending and pending.user_id is None:
            pending.user_id = update.effective_user.id
            pending.status = "activ"
            pending.activated_date = datetime.utcnow()
            await session.commit()
        # получаем уже активного пользователя
        db_user = await fetch_db_user(session, update.effective_user.id)
        role = db_user.role if db_user else "user"
    await update.message.reply_text(
        "Меню",
        reply_markup=main_menu(role)
    )

# Скрыть текущее inline-меню
async def hide_inline_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_reply_markup(reply_markup=None)

# noop для кнопок без действия
async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

# Назад в главное меню (inline → inline)
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, query.from_user.id)
        role = db_user.role if db_user else "user"
    await query.message.reply_text(
        "Меню",
        reply_markup=main_menu(role)
    )

# Подсказка: добавить пользователя
async def add_user_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "Для добавления нового пользователя пришлите его ник",
        reply_markup=add_user_menu()
    )
    context.user_data["adding_role"] = "user"
    context.user_data["inviter_id"] = query.from_user.id

# Подсказка: добавить модератора
async def add_moderator_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "Для добавления нового модератора пришлите его ник",
        reply_markup=add_moderator_menu()
    )
    context.user_data["adding_role"] = "moderator"
    context.user_data["inviter_id"] = query.from_user.id

# Основной message handler: ссылки и ввод нового пользователя
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""

    # Добавление нового пользователя/модератора
    role_to_add = context.user_data.get("adding_role")
    inviter_id = context.user_data.get("inviter_id")
    if role_to_add:
        nick = text.strip()
        normalized = re.sub(r"^(?:https?://t\.me/|t\.me/|@)", "", nick)
        async with AsyncSessionLocal() as session:
            # проверяем по username
            res = await session.execute(
                select(User).filter_by(username=normalized)
            )
            exists = res.scalar_one_or_none()
            if not exists:
                # создаём с user_id=None
                new_user = User(
                    user_id=None,
                    username=normalized,
                    role=role_to_add,
                    status="pending",
                    invited_by=inviter_id
                )
                session.add(new_user)
                await session.commit()
                role_name = "Модератор" if role_to_add == "moderator" else "Пользователь"
                await update.message.reply_text(f"{role_name} @{normalized} успешно добавлен.")
            else:
                await update.message.reply_text(f"Пользователь @{normalized} уже существует.")
        context.user_data.pop("adding_role", None)
        context.user_data.pop("inviter_id", None)
        return

    # Обработка ссылок и активации
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, user.id)
        if not db_user:
            # пытаемся активировать по username
            res = await session.execute(
                select(User).filter_by(username=user.username, status="pending")
            )
            pending = res.scalar_one_or_none()
            if pending:
                pending.user_id = user.id
                pending.status = "activ"
                pending.activated_date = datetime.utcnow()
                await session.commit()
                db_user = pending
            else:
                return  # незарегистрированные игнорим

        # дальше логика ссылок без изменений...
        links = re.findall(r"https?://\S+|t\.me/\S+|@\w+", text)
        if not links:
            session.add(Event(user_id=user.id, state="no_link"))
            await session.commit()
            await update.message.reply_text("в сообщение нет ссылок")
            return
        if len(links) > 1:
            session.add(Event(user_id=user.id, state="many_links"))
            await session.commit()
            await update.message.reply_text("пришлите одну ссылку за раз")
            return

        url = links[0]
        if db_user.transition_mode == "immediate":
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

        item = Queue(
            user_id=user.id,
            message_id=update.message.message_id,
            url=url,
            transition_time=transition_time
        )
        session.add(item)
        await session.commit()
        await update.message.reply_text("Ссылка добавлена в очередь.")

# остальные хэндлеры остаются без изменений

def register_handlers(app):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(hide_inline_menu, pattern=r"^hide_menu$"))
    app.add_handler(MessageHandler(filters.Regex("^Меню$") & ~filters.COMMAND, show_main_menu))

    app.add_handler(CallbackQueryHandler(back_to_menu,         pattern=r"^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(show_queue_cb,        pattern=r"^show_queue$"))
    app.add_handler(CallbackQueryHandler(show_stats,           pattern=r"^show_stats$"))
    app.add_handler(CallbackQueryHandler(show_history,         pattern=r"^show_history$"))
    app.add_handler(CallbackQueryHandler(show_notifications,   pattern=r"^show_notifications$"))
    app.add_handler(CallbackQueryHandler(set_notify,           pattern=r"^notify_"))
    app.add_handler(CallbackQueryHandler(show_transition_mode, pattern=r"^show_transition_mode$"))
    app.add_handler(CallbackQueryHandler(set_transition_mode,  pattern=r"^mode_"))
    app.add_handler(CallbackQueryHandler(show_users,           pattern=r"^show_users$"))
    app.add_handler(CallbackQueryHandler(add_user_prompt,      pattern=r"^add_user$"))
    app.add_handler(CallbackQueryHandler(add_moderator_prompt, pattern=r"^add_moderator$"))
    app.add_handler(CallbackQueryHandler(delete_user,          pattern=r"^del_user:"))
    app.add_handler(CallbackQueryHandler(on_delete_queue,      pattern=r"^del_queue:"))
    app.add_handler(CallbackQueryHandler(cancel,               pattern=r"^cancel$"))
    app.add_handler(CallbackQueryHandler(noop_callback,        pattern=r"^noop$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(CommandHandler("queue", on_queue))
