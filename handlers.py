import re
from datetime import datetime, timedelta
import random

from sqlalchemy import select, func
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    CommandHandler,
    filters,
)

from db import AsyncSessionLocal
from models import User, Queue, Event
from keyboards import (
    main_menu,
    queue_menu,
    notifications_menu,
    transition_mode_menu,
    users_menu,
    add_user_menu,
    add_moderator_menu,
)

# --- Message Handler ---
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    session = AsyncSessionLocal()
    # Проверка пользователя по user_id
    db_user = await session.get(User, user.id)
    if not db_user:
        # проверка по username и status='pending'
        res = await session.execute(
            select(User).filter_by(username=user.username, status='pending')
        )
        db_user = res.scalar_one_or_none()
        if db_user:
            db_user.user_id = user.id
            db_user.activated_date = datetime.utcnow()
            db_user.status = 'activ'
            await session.commit()
        else:
            session.close()
            return  # игнорируем сообщения от неизвестных

    text = update.message.text or ''
    links = re.findall(r"https?://\S+|t\.me/\S+|@\w+|\b\w+\.\w+\b", text)
    if len(links) == 0:
        await update.message.reply_text("в сообщение нет ссылок")
        session.add(Event(user_id=user.id, state='no_link'))
        await session.commit()
        session.close()
        return
    if len(links) > 1:
        await update.message.reply_text("пришлите одну ссылку за раз")
        session.add(Event(user_id=user.id, state='many_links'))
        await session.commit()
        session.close()
        return

    url = links[0]
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
            start, end = now, end_of_day
        rand_ts = start + (end - start) * random.random()
        transition_time = rand_ts

    session.add(Queue(
        user_id=user.id,
        message_id=update.message.message_id,
        url=url,
        transition_time=transition_time,
    ))
    await session.commit()
    session.close()
    await update.message.reply_text("Ссылка добавлена в очередь.")

# --- Callback Handlers ---
async def show_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = AsyncSessionLocal()
    user = update.effective_user
    res = await session.execute(select(Queue).filter_by(user_id=user.id))
    items = res.scalars().all()
    kb = queue_menu(items)
    await update.callback_query.message.reply_text("Ваша очередь:", reply_markup=kb)
    session.close()
    await update.callback_query.answer()

async def delete_queue_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, item_id = query.data.split(':')
    session = AsyncSessionLocal()
    item = await session.get(Queue, int(item_id))
    if item:
        session.delete(item)
        await session.commit()
    session.close()
    # Обновить меню
    await show_queue(update, context)

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = AsyncSessionLocal()
    user = update.effective_user
    # Всего
    total = await session.scalar(
        select(func.count()).select_from(Event).filter_by(user_id=user.id, state='success')
    )
    # За месяц
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    month = await session.scalar(
        select(func.count()).select_from(Event)
        .filter(Event.user_id==user.id, Event.state=='success', Event.timestamp>=month_start)
    )
    # За неделю
    week_start = datetime.utcnow() - timedelta(days=datetime.utcnow().weekday())
    week = await session.scalar(
        select(func.count()).select_from(Event)
        .filter(Event.user_id==user.id, Event.state=='success', Event.timestamp>=week_start)
    )
    session.close()
    text = f"Статистика:\nВсего: {total}\nЭтот месяц: {month}\nЭта неделя: {week}"
    await update.callback_query.message.reply_text(text)
    await update.callback_query.answer()

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = AsyncSessionLocal()
    user = update.effective_user
    res = await session.execute(
        select(Event)
        .filter(Event.user_id==user.id, Event.state.in_(['success','proxy_error']))
        .order_by(Event.timestamp.desc())
        .limit(20)
    )
    events = res.scalars().all()
    text = '\n'.join(f"{e.initial_url} -> {e.final_url or e.state} at {e.timestamp}" for e in events)
    session.close()
    await update.callback_query.message.reply_text(text or 'Нет записей')
    await update.callback_query.answer()

async def show_notifications_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = notifications_menu()
    await update.callback_query.message.reply_text('Уведомления:', reply_markup=kb)
    await update.callback_query.answer()

async def set_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, mode = query.data.split(':')
    session = AsyncSessionLocal()
    user = update.effective_user
    db_user = await session.get(User, user.id)
    db_user.notify_mode = mode
    await session.commit()
    session.close()
    await query.message.reply_text(f"Уведомления: {mode}")
    await query.answer()

async def show_transition_mode_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = transition_mode_menu()
    await update.callback_query.message.reply_text('Режим перехода:', reply_markup=kb)
    await update.callback_query.answer()

async def set_transition_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, mode = query.data.split(':')
    session = AsyncSessionLocal()
    user = update.effective_user
    db_user = await session.get(User, user.id)
    db_user.transition_mode = mode
    await session.commit()
    session.close()
    await query.message.reply_text(f"Режим перехода изменен на {mode}")
    await query.answer()

async def show_users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = AsyncSessionLocal()
    user = update.effective_user
    res = await session.execute(select(User))
    users = res.scalars().all()
    kb = users_menu(users, user)
    await update.callback_query.message.reply_text('Пользователи:', reply_markup=kb)
    session.close()
    await update.callback_query.answer()

async def delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, uid = query.data.split(':')
    session = AsyncSessionLocal()
    user = await session.get(User, int(uid))
    if user:
        await session.delete(user)
        await session.commit()
    session.close()
    await show_users_menu(update, context)
    await query.answer()

async def add_user_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text('Для добавления нового пользователя пришлите его ник')
    context.user_data['adding_role'] = 'user'
    await update.callback_query.answer()

async def add_moderator_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text('Для добавления нового модератора пришлите его ник')
    context.user_data['adding_role'] = 'moderator'
    await update.callback_query.answer()

async def receive_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = context.user_data.get('adding_role')
    if not role:
        return
    text = update.message.text.strip()
    username = re.sub(r"^(https?://t\.me/|t\.me/|@)", '', text)
    session = AsyncSessionLocal()
    session.add(User(username=username, role=role, status='pending', invited_by=update.effective_user.username))
    await session.commit()
    session.close()
    await update.message.reply_text(f"{role.capitalize()} @{username} успешно добавлен.")
    context.user_data.pop('adding_role', None)

async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('adding_role', None)
    await update.callback_query.message.reply_text('Операция отменена')
    await update.callback_query.answer()

# --- Registration ---
def register_handlers(app):
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(CommandHandler('queue', show_queue))

    app.add_handler(CallbackQueryHandler(show_queue, pattern='^show_queue$'))
    app.add_handler(CallbackQueryHandler(delete_queue_item, pattern=r'^del_queue:'))
    app.add_handler(CallbackQueryHandler(show_statistics, pattern='^show_stats$'))
    app.add_handler(CallbackQueryHandler(show_history, pattern='^show_history$'))

    app.add_handler(CallbackQueryHandler(show_notifications_menu, pattern='^show_notifications$'))
    app.add_handler(CallbackQueryHandler(set_notifications, pattern='^set_notify:'))

    app.add_handler(CallbackQueryHandler(show_transition_mode_menu, pattern='^show_transition_mode$'))
    app.add_handler(CallbackQueryHandler(set_transition_mode, pattern='^set_transition:'))

    app.add_handler(CallbackQueryHandler(show_users_menu, pattern='^show_users$'))
    app.add_handler(CallbackQueryHandler(delete_user, pattern=r'^del_user:'))
    app.add_handler(CallbackQueryHandler(add_user_prompt, pattern='^add_user$'))
    app.add_handler(CallbackQueryHandler(add_moderator_prompt, pattern='^add_moderator$'))
    app.add_handler(MessageHandler(filters.TEXT & filters.PrivateMessage & (filters.User(user_id=None)), receive_new_user))
    app.add_handler(CallbackQueryHandler(cancel_add, pattern='^cancel_add$'))

    # Основное меню
    app.add_handler(CommandHandler('start', lambda u,c: u.message.reply_text('Меню', reply_markup=main_menu(u.effective_user.role))))
