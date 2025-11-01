from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard():
    """Основная клавиатура меню"""
    keyboard = [
        ['📝 Добавить задачу', '📋 Мои задачи'],
        ['🔴 Важные задачи', '⏰ Срочные задачи'],
        ['✅ Завершить задачу', '🔎 Описание'],
        ['✏️ Редактировать задачу', '♻️ Восстановить задачу']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_priority_keyboard():
    """Клавиатура для выбора приоритета"""
    keyboard = [
        ['🔴 Высокий', '🟡 Средний', '🟢 Низкий']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_cancel_keyboard():
    """Клавиатура с кнопкой Отмена"""
    keyboard = [['Отмена']]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_skip_or_cancel_keyboard():
    """Клавиатура с кнопками Пропустить и Отмена"""
    keyboard = [['Пропустить', 'Отмена']]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_deadline_quick_keyboard():
    """Клавиатура для быстрого выбора дедлайна"""
    keyboard = [
        ['Сегодня', 'Завтра', 'Через 3 дня'],
        ['Выбрать дату', 'Пропустить'],
        ['Отмена']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_tasks_keyboard(tasks):
    """Inline клавиатура для списка задач"""
    keyboard = []
    for task in tasks:
        task_text = task['task'][:30] + "..." if len(task['task']) > 30 else task['task']
        keyboard.append([
            InlineKeyboardButton(
                f"✅ {task_text}", 
                callback_data=f"done_{task['id']}"
            )
        ])
    return InlineKeyboardMarkup(keyboard)

def get_confirmation_keyboard():
    """Клавиатура для подтверждения действий"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ Нет", callback_data="confirm_no")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_edit_fields_keyboard():
    """Клавиатура выбора поля для редактирования"""
    keyboard = [
        ['Заголовок', 'Приоритет'],
        ['Дедлайн', 'Описание'],
        ['Отметить выполненной', 'Завершить редактирование'],
        ['Отмена']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)


def get_completed_tasks_keyboard(tasks):
    """Inline клавиатура для списка выполненных задач (для восстановления)"""
    keyboard = []
    for task in tasks:
        task_text = task['task'][:30] + "..." if len(task['task']) > 30 else task['task']
        keyboard.append([
            InlineKeyboardButton(
                f"♻️ {task_text}",
                callback_data=f"restore_{task['id']}"
            )
        ])
    return InlineKeyboardMarkup(keyboard)