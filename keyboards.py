# keyboards.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu(role: str) -> InlineKeyboardMarkup:
    """
    Главное меню:
      - Все пользователи: Очередь, Статистика, История запросов, Уведомления, Режим перехода
      - Модераторы и админы: + Пользователи, Список задач, Сервисы, Переходы
      - Только админы: + Добавить пользователя, Добавить модератора, Добавить задачу, Удалить задачу
    """
    buttons = [
        [InlineKeyboardButton("Очередь", callback_data="show_queue")],
        [InlineKeyboardButton("Статистика", callback_data="show_stats")],
        [InlineKeyboardButton("История запросов", callback_data="show_history")],
        [InlineKeyboardButton("Уведомления", callback_data="show_notifications")],
        [InlineKeyboardButton("Режим перехода", callback_data="show_transition_mode")],
    ]

    if role in ("moderator", "admin"):
        buttons.extend([
            [InlineKeyboardButton("Пользователи", callback_data="show_users")],
            [InlineKeyboardButton("Список задач", callback_data="show_tasks")],
            [InlineKeyboardButton("Сервисы", callback_data="show_services")],
            [InlineKeyboardButton("Переходы", callback_data="show_transitions")],
        ])

    if role == "admin":
        buttons.extend([
            [InlineKeyboardButton("Добавить пользователя", callback_data="add_user")],
            [InlineKeyboardButton("Добавить модератора", callback_data="add_moderator")],
        ])

    return InlineKeyboardMarkup(buttons)

def queue_menu(items) -> InlineKeyboardMarkup:
    """
    Меню просмотра очереди: список ссылок с кнопками "Удалить" и кнопка "Назад".
    """
    buttons = []
    for item in items:
        buttons.append([
            InlineKeyboardButton("Удалить", callback_data=f"del_queue:{item.id}"),
            InlineKeyboardButton(item.url, callback_data="noop"),
        ])
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)

def notifications_menu(current_mode: str) -> InlineKeyboardMarkup:
    """
    Меню выбора режима уведомлений.
    """
    modes = [
        ("Каждый переход", "notify_each", "each"),
        ("По окончании очереди", "notify_summary", "summary"),
        ("Отключены", "notify_none", "none"),
    ]
    buttons = []
    for label, data, mode in modes:
        prefix = "✔️ " if current_mode == mode else ""
        buttons.append([InlineKeyboardButton(prefix + label, callback_data=data)])
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)

def transition_mode_menu(current_mode: str) -> InlineKeyboardMarkup:
    """
    Меню выбора режима перехода.
    """
    modes = [
        ("Сразу", "mode_immediate", "immediate"),
        ("В течение дня", "mode_daily", "daily"),
    ]
    buttons = []
    for label, data, mode in modes:
        prefix = "✔️ " if current_mode == mode else ""
        buttons.append([InlineKeyboardButton(prefix + label, callback_data=data)])
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)

def users_menu(users) -> InlineKeyboardMarkup:
    """
    Меню списка пользователей: @username + кнопка "Удалить", а также
    кнопки "Добавить пользователя", "Добавить модератора" и "Назад".
    """
    buttons = []
    for user in users:
        buttons.append([
            InlineKeyboardButton(f"@{user.username}", callback_data="noop"),
            InlineKeyboardButton("Удалить", callback_data=f"del_user:{user.user_id}"),
        ])
    buttons.append([InlineKeyboardButton("Добавить пользователя", callback_data="add_user")])
    buttons.append([InlineKeyboardButton("Добавить модератора", callback_data="add_moderator")])
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)

def tasks_menu(tasks, role: str) -> InlineKeyboardMarkup:
    """
    Меню списка задач: список задач с кнопками "Удалить" (только для админов) и кнопка "Назад".
    """
    buttons = []
    for task in tasks:
        row = [InlineKeyboardButton(task.name, callback_data="noop")]
        if role == "admin":
            row.append(InlineKeyboardButton("Удалить", callback_data=f"del_task:{task.id}"))
        buttons.append(row)
    if role == "admin":
        buttons.append([InlineKeyboardButton("Добавить задачу", callback_data="add_task")])
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)

def services_menu() -> InlineKeyboardMarkup:
    """
    Меню сервисов: список сервисов и кнопка "Назад".
    """
    buttons = [
        [InlineKeyboardButton("Сервис 1", callback_data="noop")],
        [InlineKeyboardButton("Сервис 2", callback_data="noop")],
        [InlineKeyboardButton("Назад", callback_data="back_to_menu")],
    ]
    return InlineKeyboardMarkup(buttons)

def transitions_menu() -> InlineKeyboardMarkup:
    """
    Меню переходов: список переходов и кнопка "Назад".
    """
    buttons = [
        [InlineKeyboardButton("Переход 1", callback_data="noop")],
        [InlineKeyboardButton("Переход 2", callback_data="noop")],
        [InlineKeyboardButton("Назад", callback_data="back_to_menu")],
    ]
    return InlineKeyboardMarkup(buttons)

def add_user_menu() -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой "Отмена" для ввода ника нового пользователя.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Отмена", callback_data="cancel")]
    ])

def add_moderator_menu() -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой "Отмена" для ввода ника нового модератора.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Отмена", callback_data="cancel")]
    ])

def add_task_menu() -> InlineKeyboardMarkup:
    """
    Клавиатура с кнопкой "Отмена" для ввода названия новой задачи.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Отмена", callback_data="cancel")]
    ])
