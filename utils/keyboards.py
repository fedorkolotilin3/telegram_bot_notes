from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton

def get_main_keyboard():
    """Основная клавиатура меню"""
    keyboard = [
        ['📝 Добавить задачу', '📋 Мои задачи'],
        ['🔴 Важные задачи', '⏰ Срочные задачи'],
        ['✅ Завершить задачу', '🔎 Описание'],
        ['✏️ Редактировать описание']
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_priority_keyboard():
    """Клавиатура для выбора приоритета"""
    keyboard = [
        ['🔴 Высокий', '🟡 Средний', '🟢 Низкий']
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