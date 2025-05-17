# handlers.py

import re
import random
from datetime import datetime, timedelta
from urllib.parse import urlparse

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from sqlalchemy import select, func

from db import AsyncSessionLocal
from models import User, Queue, Event
from keyboards import (
    main_menu,
    transition_mode_menu,
    users_menu,
    add_user_menu,
    add_moderator_menu,
)

# «Красная» клавиатура с кнопкой «☰ Меню»
RED_KEYBOARD = ReplyKeyboardMarkup(
    [[KeyboardButton("☰ Меню")]],
    resize_keyboard=True,
)

def shorten_url(full_url: str, max_len: int = 30) -> str:
    """
    Обрезает протокол и сокращает URL до max_len символов:
    домен + суффикс + … + последние символы.
    """
    parsed = urlparse(full_url)
    rest = parsed.netloc + parsed.path + (f"?{parsed.query}" if parsed.query else "")
    if len(rest) <= max_len:
        return rest
    tail_len = max_len - len(parsed.netloc) - 1
    tail = rest[-tail_len:] if tail_len > 0 else rest[:max_len]
    return f"{parsed.netloc}…{tail}"

async def fetch_db_user(session, telegram_id: int):
    """Возвращает объект User по Telegram ID или None."""
    result = await session.execute(
        select(User).filter_by(user_id=telegram_id)
    )
    return result.scalar_one_or_none()

# /start
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as session:
        pending = (await session.execute(
            select(User).filter_by(
                username=update.effective_user.username,
                status="pending"
            )
        )).scalar_one_or_none()
        db_user = pending or await fetch_db_user(session, update.effective_user.id)
        if not db_user:
            return
        if pending and pending.user_id is None:
            pending.user_id = update.effective_user.id
            pending.status = "activ"
            pending.activated_date = datetime.now()
            await session.commit()
        await update.message.reply_text("Меню", reply_markup=RED_KEYBOARD)

# Текстовая «☰ Меню» → inline-меню
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as session:
        pending = (await session.execute(
            select(User).filter_by(
                username=update.effective_user.username,
                status="pending"
            )
        )).scalar_one_or_none()
        db_user = pending or await fetch_db_user(session, update.effective_user.id)
        if not db_user:
            return
        if pending and pending.user_id is None:
            pending.user_id = update.effective_user.id
            pending.status = "activ"
            pending.activated_date = datetime.now()
            await session.commit()
        role = db_user.role
        await update.message.reply_text("Меню", reply_markup=main_menu(role))

# Скрыть текущее inline-меню
async def hide_inline_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_reply_markup(reply_markup=None)

# Назад в главное меню
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, query.from_user.id)
        if not db_user:
            return
        role = db_user.role
        await query.message.edit_text("Меню", reply_markup=main_menu(role))

# noop
async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

# Подменю «Режим перехода»
async def show_transition_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, query.from_user.id)
        if not db_user:
            return
        mode = db_user.transition_mode
        await query.message.edit_text("Переходы", reply_markup=transition_mode_menu(mode))

async def set_transition_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mode = {"mode_immediate": "immediate", "mode_daily": "daily"}[query.data]
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, query.from_user.id)
        if not db_user:
            return
        db_user.transition_mode = mode
        await session.commit()
        await query.message.edit_text("Переходы", reply_markup=transition_mode_menu(mode))

# Обновлённое меню «Очередь»
async def on_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        send = query.message.edit_text
        user_id = query.from_user.id
    else:
        send = update.effective_message.reply_text
        user_id = update.effective_user.id

    async with AsyncSessionLocal() as session:
        items = (await session.execute(
            select(Queue)
            .where(
                Queue.user_id == user_id,
                Queue.status.in_(["pending", "in_progress"])
            )
            .order_by(Queue.transition_time)
        )).scalars().all()

    buttons = []
    for idx, item in enumerate(items):
        # Ссылка (сокращённый текст, полная URL по нажатию)
        short = shorten_url(item.url)
        buttons.append([InlineKeyboardButton(short, url=item.url)])

        if item.status == "pending":
            t = item.transition_time.strftime("%H:%M %d.%m")
            buttons.append([
                InlineKeyboardButton(t, callback_data="noop"),
                InlineKeyboardButton("удалить", callback_data=f"del_queue:{item.id}")
            ])
        elif item.status == "in_progress":
            buttons.append([InlineKeyboardButton("в процессе перехода", callback_data="noop")])

        # разделитель между блоками (кроме последнего)
        if idx < len(items) - 1:
            buttons.append([InlineKeyboardButton("──────────────────", callback_data="noop")])

    # кнопка «Назад»
    buttons.append([InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")])

    await send("Ваша очередь:", reply_markup=InlineKeyboardMarkup(buttons))

# Удалить из очереди
async def on_delete_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, sid = query.data.split(":", 1)
    async with AsyncSessionLocal() as session:
        item = await session.get(Queue, int(sid))
        if item and item.status != "in_progress":
            await session.delete(item)
            await session.commit()
    # Перерисовать очередь
    await on_queue(update, context)

# Статистика
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    now = datetime.now()
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        total = (await session.execute(
            select(func.count()).select_from(Event)
            .filter_by(user_id=user_id, state="success")
        )).scalar() or 0

        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month = (await session.execute(
            select(func.count()).select_from(Event)
            .filter(
                Event.user_id == user_id,
                Event.state == "success",
                Event.timestamp >= month_start
            )
        )).scalar() or 0

        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        week = (await session.execute(
            select(func.count()).select_from(Event)
            .filter(
                Event.user_id == user_id,
                Event.state == "success",
                Event.timestamp >= week_start
            )
        )).scalar() or 0

    text = (
        f"Статистика:\n"
        f"Всего переходов: {total}\n"
        f"В этом месяце: {month}\n"
        f"На этой неделе: {week}"
    )
    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")]])
    await query.message.edit_text(text, reply_markup=back_kb)

# История запросов
async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        events = (await session.execute(
            select(Event)
            .filter(
                Event.user_id == user_id,
                Event.state.in_(["success", "proxy_error"])
            )
            .order_by(Event.timestamp.desc())
            .limit(20)
        )).scalars().all()

    if not events:
        text = "История запросов пуста"
    else:
        lines = []
        for e in events:
            ts = e.timestamp.strftime("%Y-%m-%d %H:%M")
            init_short = shorten_url(e.initial_url)
            init_link  = f'<a href="{e.initial_url}">{init_short}</a>'
            if e.state == "success":
                final_short = shorten_url(e.final_url)
                final_link  = f'<a href="{e.final_url}">{final_short}</a>'
                lines.append(f"{ts}: {init_link} → {final_link}")
            else:
                lines.append(f"{ts}: {init_link} ({e.state})")
        text = "История запросов:\n" + "\n".join(lines)

    back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data="back_to_menu")]])
    await query.message.edit_text(
        text,
        reply_markup=back_kb,
        disable_web_page_preview=True,
        parse_mode="HTML"
    )

# Пользователи
async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with AsyncSessionLocal() as session:
        users = (await session.execute(select(User).order_by(User.role))).scalars().all()
    await query.message.edit_text("Пользователи", reply_markup=users_menu(users))

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, sid = query.data.split(":", 1)
    async with AsyncSessionLocal() as session:
        db_actor = await fetch_db_user(session, query.from_user.id)
        db_target = await fetch_db_user(session, int(sid))
        if db_actor and db_target:
            order = {"user": 1, "moderator": 2, "admin": 3}
            if order[db_actor.role] > order[db_target.role]:
                await session.delete(db_target)
                await session.commit()
                users = (await session.execute(select(User).order_by(User.role))).scalars().all()
                await query.message.edit_text("Пользователи", reply_markup=users_menu(users))

# Добавление пользователя / модератора
async def add_user_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "Для добавления нового пользователя пришлите его ник",
        reply_markup=add_user_menu()
    )
    context.user_data["adding_role"] = "user"
    context.user_data["inviter_id"] = query.from_user.id

async def add_moderator_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.edit_text(
        "Для добавения нового модератора пришлите его ник",
        reply_markup=add_moderator_menu()
    )
    context.user_data["adding_role"] = "moderator"
    context.user_data["inviter_id"] = query.from_user.id

# Основной message handler
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""

    role_to_add = context.user_data.get("adding_role")
    inviter_id = context.user_data.get("inviter_id")
    if role_to_add:
        normalized = re.sub(r"^(?:https?://t\.me/|t\.me/|@)", "", text.strip())
        async with AsyncSessionLocal() as session:
            exists = (await session.execute(
                select(User).filter_by(username=normalized)
            )).scalar_one_or_none()
            if not exists:
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
                await update.message.reply_text(f"{role_name} @{normalized} успешно добавлен")
            else:
                await update.message.reply_text(f"Пользователь @{normalized} уже существует")
        context.user_data.pop("adding_role", None)
        context.user_data.pop("inviter_id", None)
        return

    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, user.id)
        if not db_user:
            pending = (await session.execute(
                select(User).filter_by(username=user.username, status="pending")
            )).scalar_one_or_none()
            if pending:
                pending.user_id = user.id
                pending.status = "activ"
                pending.activated_date = datetime.now()
                await session.commit()
                db_user = pending
            else:
                return

        links = re.findall(r"https?://\S+|t\.me/\S+|@\w+", text)
        if not links:
            session.add(Event(user_id=user.id, state="no_link"))
            await session.commit()
            await update.message.reply_text("В сообщение нет ссылок")
            return
        if len(links) > 1:
            session.add(Event(user_id=user.id, state="many_links"))
            await session.commit()
            await update.message.reply_text("Пришлите одну ссылку за раз")
            return

        url = links[0]
        if db_user.transition_mode == "immediate":
            transition_time = datetime.now()
        else:
            now = datetime.now()
            end_of_day = now.replace(hour=23, minute=59, second=59)
            if (end_of_day - now) < timedelta(hours=2):
                tomorrow = now + timedelta(days=1)
                start = tomorrow.replace(hour=0, minute=0, second=0)
                end = tomorrow.replace(hour=23, minute=59, second=59)
            else:
                start = now
                end = end_of_day
            transition_time = start + (end - start) * random.random()

        session.add(Queue(
            user_id=user.id,
            message_id=update.message.message_id,
            url=url,
            transition_time=transition_time
        ))
        await session.commit()

        await update.message.reply_text(
            "Ссылка добавлена в очередь ⏳",
            reply_to_message_id=update.message.message_id
        )

# Отмена
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("adding_role", None)
    context.user_data.pop("inviter_id", None)
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, query.from_user.id)
        if not db_user:
            return
        role = db_user.role
        await query.message.edit_text("Отменено", reply_markup=main_menu(role))

def register_handlers(app):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(hide_inline_menu, pattern=r"^hide_menu$"))
    app.add_handler(MessageHandler(filters.Regex("^☰ Меню$") & ~filters.COMMAND, show_main_menu))

    app.add_handler(CallbackQueryHandler(back_to_menu, pattern=r"^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(on_queue, pattern=r"^show_queue$"))
    app.add_handler(CallbackQueryHandler(on_delete_queue, pattern=r"^del_queue:"))
    app.add_handler(CallbackQueryHandler(show_stats, pattern=r"^show_stats$"))
    app.add_handler(CallbackQueryHandler(show_history, pattern=r"^show_history$"))
    app.add_handler(CallbackQueryHandler(show_transition_mode, pattern=r"^show_transition_mode$"))
    app.add_handler(CallbackQueryHandler(set_transition_mode, pattern=r"^mode_"))
    app.add_handler(CallbackQueryHandler(show_users, pattern=r"^show_users$"))
    app.add_handler(CallbackQueryHandler(add_user_prompt, pattern=r"^add_user$"))
    app.add_handler(CallbackQueryHandler(add_moderator_prompt, pattern=r"^add_moderator$"))
    app.add_handler(CallbackQueryHandler(delete_user, pattern=r"^del_user:"))
    app.add_handler(CallbackQueryHandler(cancel, pattern=r"^cancel$"))
    app.add_handler(CallbackQueryHandler(noop_callback, pattern=r"^noop$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(CommandHandler("queue", on_queue))
