# keyboards.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu(role: str) -> InlineKeyboardMarkup:
    """
    Главное inline-меню:
      - Все пользователи: Очередь, Статистика, История, Режим перехода, Скрыть меню
      - Модераторы и админы: + Пользователи
    """
    buttons = [
        [
            InlineKeyboardButton("Очередь", callback_data="show_queue"),
            InlineKeyboardButton("Статистика", callback_data="show_stats"),
        ],
        [
            InlineKeyboardButton("История", callback_data="show_history"),
            InlineKeyboardButton("Режим перехода", callback_data="show_transition_mode"),
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


def queue_menu(items) -> InlineKeyboardMarkup:
    """
    Меню просмотра очереди: ссылки + кнопка «Удалить» и «Назад»
    """
    buttons = []
    for item in items:
        buttons.append([
            InlineKeyboardButton("Удалить", callback_data=f"del_queue:{item.id}"),
            InlineKeyboardButton(item.url, callback_data="noop"),
        ])
    buttons.append([InlineKeyboardButton("Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(buttons)


def transition_mode_menu(current_mode: str) -> InlineKeyboardMarkup:
    """
    Подменю «Режим перехода»: выбор режима + «Назад»
    """
    modes = [
        ("Сразу",                 "mode_immediate", "immediate"),
        ("Случайно в течение дня", "mode_daily",     "daily"),
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
