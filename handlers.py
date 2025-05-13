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
from sqlalchemy import select, func

from db import AsyncSessionLocal
from models import User, Queue, Event
from keyboards import (
    main_menu,
    queue_menu,
    notifications_menu,
    transition_mode_menu,
    users_menu,
    add_user_menu,
    add_moderator_menu
)

# /start
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Меню",
        reply_markup=main_menu(update.effective_user.role)
    )

# noop для кнопок без действия
async def noop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

# Назад в главное меню
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
    await update.callback_query.message.reply_text(
        "Меню",
        reply_markup=main_menu(db_user.role if db_user else "user")
    )

# Подсказка: добавить пользователя
async def add_user_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Для добавления нового пользователя пришлите его ник",
        reply_markup=add_user_menu()
    )
    context.user_data["adding_role"] = "user"
    context.user_data["inviter_id"] = update.effective_user.id

# Подсказка: добавить модератора
async def add_moderator_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(
        "Для добавления нового модератора пришлите его ник",
        reply_markup=add_moderator_menu()
    )
    context.user_data["adding_role"] = "moderator"
    context.user_data["inviter_id"] = update.effective_user.id

# Основной message handler: ссылки и ввод нового пользователя
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""

    # --- Флоу добавления нового пользователя/модератора ---
    role_to_add = context.user_data.get("adding_role")
    inviter_id = context.user_data.get("inviter_id")
    if role_to_add:
        nick = text.strip()
        normalized = re.sub(r"^(?:https?://t\.me/|t\.me/|@)", "", nick)
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(User).filter_by(username=normalized)
            )
            exists = res.scalar_one_or_none()
            if not exists:
                new_user = User(
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

    # --- Обычная обработка ссылок ---
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        if not db_user:
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
                return  # игнорировать незарегистрированных

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

# Показать очередь (из кнопки и /queue)
async def on_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Queue).filter_by(user_id=user.id)
        )
        items = res.scalars().all()
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
    await on_queue(update, context)

# Статистика
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = update.effective_user
    now = datetime.utcnow()
    async with AsyncSessionLocal() as session:
        total = (await session.execute(
            select(func.count()).select_from(Event)
              .filter_by(user_id=user.id, state="success")
        )).scalar() or 0
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month = (await session.execute(
            select(func.count()).select_from(Event)
              .filter(Event.user_id==user.id, Event.state=="success", Event.timestamp>=month_start)
        )).scalar() or 0
        week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        week = (await session.execute(
            select(func.count()).select_from(Event)
              .filter(Event.user_id==user.id, Event.state=="success", Event.timestamp>=week_start)
        )).scalar() or 0
    text = (
        f"Статистика:\n"
        f"Всего переходов: {total}\n"
        f"В этом месяце: {month}\n"
        f"На этой неделе: {week}"
    )
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
    await update.callback_query.message.reply_text(text, reply_markup=main_menu(db_user.role))

# История запросов
async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Event)
              .filter(Event.user_id==user.id, Event.state.in_(["success","proxy_error"]))
              .order_by(Event.timestamp.desc())
              .limit(20)
        )
        events = res.scalars().all()
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
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
    await update.callback_query.message.reply_text(text, reply_markup=main_menu(db_user.role))

# Уведомления
async def show_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
    kb = notifications_menu(db_user.notify_mode)
    await update.callback_query.message.reply_text("Уведомления", reply_markup=kb)

async def set_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    mode = {
        "notify_each": "each",
        "notify_summary": "summary",
        "notify_none": "none"
    }[update.callback_query.data]
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        db_user.notify_mode = mode
        await session.commit()
    labels = {"each": "Каждый переход", "summary": "По окончании очереди", "none": "Отключены"}
    await update.callback_query.message.reply_text(
        f"Уведомления: {labels[mode]}", reply_markup=main_menu(db_user.role)
    )

# Режим перехода
async def show_transition_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
    kb = transition_mode_menu(db_user.transition_mode)
    await update.callback_query.message.reply_text("Режим перехода", reply_markup=kb)

async def set_transition_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    mode = {
        "mode_immediate": "immediate",
        "mode_daily": "daily"
    }[update.callback_query.data]
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
        db_user.transition_mode = mode
        await session.commit()
    labels = {"immediate": "Сразу", "daily": "В течение дня"}
    await update.callback_query.message.reply_text(
        f"Режим перехода: {labels[mode]}", reply_markup=main_menu(db_user.role)
    )

# Пользователи
async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(User).order_by(User.role))
        all_users = res.scalars().all()
    await update.callback_query.message.reply_text("Пользователи", reply_markup=users_menu(all_users))

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    _, sid = update.callback_query.data.split(":")
    target_id = int(sid)
    actor = update.effective_user
    async with AsyncSessionLocal() as session:
        db_actor = await session.get(User, actor.id)
        db_target = await session.get(User, target_id)
        if not db_target:
            await update.callback_query.message.reply_text("Пользователь не найден.")
            return
        if db_target.user_id == actor.id:
            await update.callback_query.message.reply_text("Нельзя удалить себя.")
            return
        order = {"user": 1, "moderator": 2, "admin": 3}
        if order[db_actor.role] <= order[db_target.role]:
            await update.callback_query.message.reply_text("Нет прав на удаление пользователя.")
            return
        await session.delete(db_target)
        await session.commit()
    # Обновляем список
    await show_users(update, context)

# Отмена
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    context.user_data.pop("adding_role", None)
    context.user_data.pop("inviter_id", None)
    user = update.effective_user
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, user.id)
    await update.callback_query.message.reply_text(
        "Отменено", reply_markup=main_menu(db_user.role if db_user else "user")
    )

def register_handlers(app):
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern=r"^back_to_menu$"))
    app.add_handler(CallbackQueryHandler(show_queue_cb, pattern=r"^show_queue$"))
    app.add_handler(CallbackQueryHandler(show_stats, pattern=r"^show_stats$"))
    app.add_handler(CallbackQueryHandler(show_history, pattern=r"^show_history$"))
    app.add_handler(CallbackQueryHandler(show_notifications, pattern=r"^show_notifications$"))
    app.add_handler(CallbackQueryHandler(set_notify, pattern=r"^notify_"))
    app.add_handler(CallbackQueryHandler(show_transition_mode, pattern=r"^show_transition_mode$"))
    app.add_handler(CallbackQueryHandler(set_transition_mode, pattern=r"^mode_"))
    app.add_handler(CallbackQueryHandler(show_users, pattern=r"^show_users$"))
    app.add_handler(CallbackQueryHandler(add_user_prompt, pattern=r"^add_user$"))
    app.add_handler(CallbackQueryHandler(add_moderator_prompt, pattern=r"^add_moderator$"))
    app.add_handler(CallbackQueryHandler(delete_user, pattern=r"^del_user:"))
    app.add_handler(CallbackQueryHandler(on_delete_queue, pattern=r"^del_queue:"))
    app.add_handler(CallbackQueryHandler(cancel, pattern=r"^cancel$"))
    app.add_handler(CallbackQueryHandler(noop_callback, pattern=r"^noop$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(CommandHandler("queue", on_queue))
