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
    """Возвращает объект User по Telegram ID или None."""
    result = await session.execute(
        select(User).filter_by(user_id=telegram_id)
    )
    return result.scalar_one_or_none()


# /start
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as session:
        # Ищем pending-запись по username
        pending = (await session.execute(
            select(User).filter_by(username=update.effective_user.username, status="pending")
        )).scalar_one_or_none()
        # Ищем уже активного по user_id
        db_user = pending or await fetch_db_user(session, update.effective_user.id)
        if not db_user:
            # Незарегистрированный — игнорируем
            return
        if pending and pending.user_id is None:
            pending.user_id = update.effective_user.id
            pending.status = "activ"
            pending.activated_date = datetime.now()
            await session.commit()
    await update.message.reply_text("Меню", reply_markup=RED_KEYBOARD)


# Текстовая «Меню» → inline-меню
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with AsyncSessionLocal() as session:
        pending = (await session.execute(
            select(User).filter_by(username=update.effective_user.username, status="pending")
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


# noop для кнопок без действия
async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


# Подменю «Настройки»
async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, query.from_user.id)
        if not db_user:
            return
    await query.message.reply_text("Настройки", reply_markup=settings_menu())


# Назад в главное меню (inline → inline)
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, query.from_user.id)
        if not db_user:
            return
        role = db_user.role
    await query.message.reply_text("Меню", reply_markup=main_menu(role))


# Обработчик «Очередь» из inline-меню
async def show_queue_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, query.from_user.id)
        if not db_user:
            return
    await on_queue(update, context)


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

    # Флоу добавления нового пользователя/модератора
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
                await update.message.reply_text(f"{role_name} @{normalized} успешно добавлен.")
            else:
                await update.message.reply_text(f"Пользователь @{normalized} уже существует.")
        context.user_data.pop("adding_role", None)
        context.user_data.pop("inviter_id", None)
        return

    # Обработка ссылок и активация pending-аккаунта
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
                return  # незарегистрированные игнорируем

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

        item = Queue(
            user_id=user.id,
            message_id=update.message.message_id,
            url=url,
            transition_time=transition_time
        )
        session.add(item)
        await session.commit()
        await update.message.reply_text("Ссылка добавлена в очередь.")


# Показать очередь
async def on_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, user.id)
        if not db_user:
            return
        items = (await session.execute(
            select(Queue).filter_by(user_id=user.id)
        )).scalars().all()
    kb = queue_menu(items)
    await update.effective_message.reply_text("Ваша очередь:", reply_markup=kb)


# Удалить из очереди
async def on_delete_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, sid = query.data.split(":")
    async with AsyncSessionLocal() as session:
        item = await session.get(Queue, int(sid))
        if item:
            await session.delete(item)
            await session.commit()
    await show_queue_cb(update, context)


# Статистика
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    now = datetime.now()
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, user_id)
        if not db_user:
            return
        total = (await session.execute(
            select(func.count()).select_from(Event).filter_by(user_id=user_id, state="success")
        )).scalar() or 0
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month = (await session.execute(
            select(func.count()).select_from(Event)
                .filter(Event.user_id==user_id, Event.state=="success", Event.timestamp>=month_start)
        )).scalar() or 0
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        week = (await session.execute(
            select(func.count()).select_from(Event)
                .filter(Event.user_id==user_id, Event.state=="success", Event.timestamp>=week_start)
        )).scalar() or 0
    text = (
        f"Статистика:\n"
        f"Всего переходов: {total}\n"
        f"В этом месяце: {month}\n"
        f"На этой неделе: {week}"
    )
    await query.message.reply_text(text, reply_markup=main_menu(db_user.role))


# История запросов
async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, user_id)
        if not db_user:
            return
        events = (await session.execute(
            select(Event)
                .filter(Event.user_id==user_id, Event.state.in_(["success","proxy_error"]))
                .order_by(Event.timestamp.desc())
                .limit(20)
        )).scalars().all()
    if not events:
        text = "История запросов пуста."
    else:
        lines = []
        for e in events:
            ts = e.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            if e.state == "success":
                lines.append(f"{ts}: {e.initial_url} → {e.final_url}")
            else:
                lines.append(f"{ts}: {e.initial_url} ({e.state})")
        text = "История запросов:\n" + "\n".join(lines)
    await query.message.reply_text(text, reply_markup=main_menu(db_user.role))


# Уведомления
async def show_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, user_id)
        if not db_user:
            return
        mode = db_user.notify_mode
    await query.message.reply_text("Уведомления", reply_markup=notifications_menu(mode))


async def set_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    mode = {
        "notify_each": "each",
        "notify_summary": "summary",
        "notify_none": "none"
    }[query.data]
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, user_id)
        if not db_user:
            return
        db_user.notify_mode = mode
        await session.commit()
    labels = {"each": "Каждый переход", "summary": "По окончании очереди", "none": "Отключены"}
    await query.message.reply_text(f"Уведомления: {labels[mode]}", reply_markup=main_menu(db_user.role))


# Режим перехода
async def show_transition_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, user_id)
        if not db_user:
            return
        mode = db_user.transition_mode
    await query.message.reply_text("Переходы", reply_markup=transition_mode_menu(mode))


async def set_transition_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    mode = {
        "mode_immediate": "immediate",
        "mode_daily": "daily"
    }[query.data]
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, user_id)
        if not db_user:
            return
        db_user.transition_mode = mode
        await session.commit()
    labels = {"immediate": "Сразу", "daily": "В течение дня"}
    await query.message.reply_text(f"Переходы: {labels[mode]}", reply_markup=main_menu(db_user.role))


# Пользователи
async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    async with AsyncSessionLocal() as session:
        db_user = await fetch_db_user(session, query.from_user.id)
        if not db_user:
            return
        users = (await session.execute(select(User).order_by(User.role))).scalars().all()
    await query.message.reply_text("Пользователи", reply_markup=users_menu(users))


async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    _, sid = query.data.split(":")
    target_id = int(sid)
    async with AsyncSessionLocal() as session:
        db_actor = await fetch_db_user(session, user_id)
        db_target = await fetch_db_user(session, target_id)
        if not db_actor or not db_target:
            return
        order = {"user": 1, "moderator": 2, "admin": 3}
        if order[db_actor.role] <= order[db_target.role]:
            await query.message.reply_text("Нет прав на удаление пользователя.")
            return
        await session.delete(db_target)
        await session.commit()
    await show_users(update, context)


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
    await query.message.reply_text("Отменено", reply_markup=main_menu(role))


def register_handlers(app):
    app.add_handler(CommandHandler("start", start_cmd))

    app.add_handler(CallbackQueryHandler(hide_inline_menu, pattern=r"^hide_menu$"))
    app.add_handler(CallbackQueryHandler(show_settings,  pattern=r"^show_settings$"))
    app.add_handler(MessageHandler(filters.Regex("^Меню$") & ~filters.COMMAND, show_main_menu))

    app.add_handler(CallbackQueryHandler(back_to_menu,        pattern=r"^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(show_queue_cb,       pattern=r"^show_queue$"))
    app.add_handler(CallbackQueryHandler(show_stats,          pattern=r"^show_stats$"))
    app.add_handler(CallbackQueryHandler(show_history,        pattern=r"^show_history$"))
    app.add_handler(CallbackQueryHandler(show_notifications,  pattern=r"^show_notifications$"))
    app.add_handler(CallbackQueryHandler(set_notify,          pattern=r"^notify_"))
    app.add_handler(CallbackQueryHandler(show_transition_mode,pattern=r"^show_transition_mode$"))
    app.add_handler(CallbackQueryHandler(set_transition_mode, pattern=r"^mode_"))
    app.add_handler(CallbackQueryHandler(show_users,          pattern=r"^show_users$"))
    app.add_handler(CallbackQueryHandler(add_user_prompt,     pattern=r"^add_user$"))
    app.add_handler(CallbackQueryHandler(add_moderator_prompt,pattern=r"^add_moderator$"))
    app.add_handler(CallbackQueryHandler(delete_user,         pattern=r"^del_user:"))
    app.add_handler(CallbackQueryHandler(on_delete_queue,     pattern=r"^del_queue:"))
    app.add_handler(CallbackQueryHandler(cancel,              pattern=r"^cancel$"))
    app.add_handler(CallbackQueryHandler(noop_callback,       pattern=r"^noop$"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(CommandHandler("queue", on_queue))
