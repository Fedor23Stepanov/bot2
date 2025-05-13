# keyboards.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def main_menu(role: str) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton('Очередь', callback_data='show_queue')]
    if role in ('moderator','admin'):
        buttons.append(InlineKeyboardButton('Пользователи', callback_data='show_users'))
    buttons.extend([
        InlineKeyboardButton('Статистика', callback_data='show_stats'),
        InlineKeyboardButton('История запросов', callback_data='show_history'),
        InlineKeyboardButton('Уведомления', callback_data='show_notifications'),
        InlineKeyboardButton('Режим перехода', callback_data='show_transition_mode'),
    ])
    return InlineKeyboardMarkup.from_column(buttons)


def queue_menu(items) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        buttons.append(
            [InlineKeyboardButton(item.url, url=item.url),
             InlineKeyboardButton('Удалить', callback_data=f'del_queue:{item.id}')]
        )
    return InlineKeyboardMarkup(buttons)


def notifications_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup.from_column([
        InlineKeyboardButton('Каждый переход', callback_data='set_notify:each'),
        InlineKeyboardButton('По окончании очереди', callback_data='set_notify:summary'),
        InlineKeyboardButton('Отключены', callback_data='set_notify:none'),
    ])


def transition_mode_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup.from_column([
        InlineKeyboardButton('Сразу', callback_data='set_transition:immediate'),
        InlineKeyboardButton('В течение дня', callback_data='set_transition:daily'),
    ])


def users_menu(users, current_user) -> InlineKeyboardMarkup:
    buttons = []
    for u in users:
        if u.user_id != current_user.id and \
           (current_user.role=='admin' or (current_user.role=='moderator' and u.role=='user')):
            buttons.append(
                [InlineKeyboardButton(f'@{u.username}', callback_data='noop'),
                 InlineKeyboardButton('Удалить', callback_data=f'del_user:{u.user_id}')]
            )
        else:
            buttons.append([InlineKeyboardButton(f'@{u.username}', callback_data='noop')])
    buttons.append([InlineKeyboardButton('Добавить пользователя', callback_data='add_user')])
    if current_user.role=='admin':
        buttons.append([InlineKeyboardButton('Добавить модератора', callback_data='add_moderator')])
    return InlineKeyboardMarkup(buttons)


def add_user_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup.from_button(
        InlineKeyboardButton('Отмена', callback_data='cancel_add')
    )

def add_moderator_menu() -> InlineKeyboardMarkup:
    return add_user_menu()  # аналогично
