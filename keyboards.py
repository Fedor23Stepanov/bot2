# keyboards.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu(role: str) -> InlineKeyboardMarkup:
    """
    Главное inline-меню:
      - Все пользователи: Очередь, Статистика, История, Настройки, Скрыть меню
      - Модераторы и админы: + Пользователи
    """
    buttons = [
        [
            InlineKeyboardButton("Очередь", callback_data="show_queue"),
            InlineKeyboardButton("Статистика", callback_data="show_stats"),
        ],
        [
            InlineKeyboardButton("История", callback_data="show_history"),
            InlineKeyboardButton("Настройки", callback_data="show_settings"),
        ],
    ]

    if role in ("moderator", "admin"):
        buttons.append([
            InlineKeyboardButton("Пользователи", callback_data="show_users")
        ])

    buttons.append([
        InlineKeyboardButton("Скрыть меню", callback_data="hide_menu")
    ])

    return InlineKeyboardMarkup(buttons)


def settings_menu() -> InlineKeyboardMarkup:
    """
    Подменю «Настройки»: Уведомления и Переходы
    """
    buttons = [
        [InlineKeyboardButton("Уведомления", callback_data="show_notifications")],
        [InlineKeyboardButton("Переходы",    callback_data="show_transition_mode")],
        [InlineKeyboardButton("Назад",       callback_data="back_to_menu")],
    ]
    return InlineKeyboardMarkup(buttons)


def queue_menu(items) -> InlineKeyboardMarkup:
    """
    Меню просмотра очереди: ссылки + кнопка «Удалить» и «Назад»
    """
    buttons = []
    for item in items:
        buttons.append([
            InlineKeyboardButton("Удалить",    callback_data=f"del_queue:{item.id}"),
            InlineKeyboardButton(item.url,     callback_data="noop"),
        ])
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)


def notifications_menu(current_mode: str) -> InlineKeyboardMarkup:
    """
    Подменю «Уведомления»: выбор режима + «Назад»
    """
    modes = [
        ("Каждый переход",      "notify_each",   "each"),
        ("По окончании очереди", "notify_summary","summary"),
        ("Отключены",            "notify_none",   "none"),
    ]
    buttons = []
    for label, data, mode in modes:
        prefix = "✔️ " if current_mode == mode else ""
        buttons.append([InlineKeyboardButton(prefix + label, callback_data=data)])
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)


def transition_mode_menu(current_mode: str) -> InlineKeyboardMarkup:
    """
    Подменю «Переходы»: выбор режима + «Назад»
    """
    modes = [
        ("Сразу",                     "mode_immediate", "immediate"),
        ("Случайно в течение дня",     "mode_daily",     "daily"),
    ]
    buttons = []
    for label, data, mode in modes:
        prefix = "✔️ " if current_mode == mode else ""
        buttons.append([InlineKeyboardButton(prefix + label, callback_data=data)])
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)


def users_menu(users) -> InlineKeyboardMarkup:
    """
    Меню «Пользователи»: список @username + «Удалить», 
    затем «Добавить пользователя», «Добавить модератора», «Назад».
    (Появляется только у модераторов и админов; 
     кнопку «Добавить модератора» можно скрыть в handlers.py для модераторов.)
    """
    buttons = []
    for user in users:
        buttons.append([
            InlineKeyboardButton(f"@{user.username}", callback_data="noop"),
            InlineKeyboardButton("Удалить",            callback_data=f"del_user:{user.user_id}"),
        ])
    buttons.append([InlineKeyboardButton("Добавить пользователя", callback_data="add_user")])
    buttons.append([InlineKeyboardButton("Добавить модератора",  callback_data="add_moderator")])
    buttons.append([InlineKeyboardButton("Назад",                  callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)


def add_user_menu() -> InlineKeyboardMarkup:
    """
    Клавиатура при вводе ника нового пользователя: «Отмена»
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Отмена", callback_data="cancel")]
    ])


def add_moderator_menu() -> InlineKeyboardMarkup:
    """
    Клавиатура при вводе ника нового модератора: «Отмена»
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Отмена", callback_data="cancel")]
    ])
