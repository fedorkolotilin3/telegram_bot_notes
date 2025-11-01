from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from database.supabase_client import db
from utils.keyboards import get_tasks_keyboard, get_main_keyboard, get_edit_fields_keyboard, get_priority_keyboard, get_completed_tasks_keyboard
from datetime import datetime
from datetime import time as dt_time
from utils.notes import update_note

# States for description-related conversations
DESC_QUERY, EDIT_SELECT, EDIT_TEXT = range(3)
# States for general edit flow (start after prior states)
EDIT_TASK_SELECT, EDIT_FIELD_SELECT, EDIT_FIELD_VALUE = range(3, 6)

def format_task(task):
    """Форматирование задачи для отображения"""
    task_id = task['id']
    task_text = task['task']
    priority_emoji = {
        'high': '🔴',
        'medium': '🟡', 
        'low': '🟢'
    }.get(task['priority'], '⚪')
    
    deadline_text = ""
    if task['deadline']:
        try:
            # parse ISO datetime or date
            deadline = datetime.fromisoformat(task['deadline'].replace('Z', '+00:00'))
            date_part = deadline.strftime('%d.%m.%Y')
            # include time if it's not midnight
            time_part = ''
            if deadline.time() != dt_time(0, 0):
                time_part = f" {deadline.strftime('%H:%M')}"
            deadline_text = f" | ⏰ {date_part}{time_part}"
        except:
            deadline_text = " | ⏰ Неверная дата"
    
    return f"*{task_id}*. {priority_emoji} {task_text}{deadline_text}"

async def show_my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все задачи пользователя"""
    user_id = update.effective_user.id
    tasks = db.get_tasks(user_id, done=False)
    
    if not tasks:
        await update.message.reply_text(
            "🎉 У вас нет активных задач!",
            reply_markup=get_main_keyboard()
        )
        return
    
    tasks_text = "\n".join([format_task(task) for task in tasks])
    message = f"📋 *Ваши активные задачи:*\n\n{tasks_text}"
    
    await update.message.reply_text(
        message,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

async def show_important_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать важные задачи"""
    user_id = update.effective_user.id
    tasks = db.get_priority_tasks(user_id, "high")
    
    if not tasks:
        await update.message.reply_text(
            "✅ Нет задач с высоким приоритетом!",
            reply_markup=get_main_keyboard()
        )
        return
    
    tasks_text = "\n".join([format_task(task) for task in tasks])
    message = f"🔴 *Задачи с высоким приоритетом:*\n\n{tasks_text}"
    
    await update.message.reply_text(
        message,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

async def show_urgent_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать срочные задачи"""
    user_id = update.effective_user.id
    tasks = db.get_urgent_tasks(user_id)
    
    if not tasks:
        await update.message.reply_text(
            "✅ Нет срочных задач на ближайшие дни!",
            reply_markup=get_main_keyboard()
        )
        return
    
    tasks_text = "\n".join([format_task(task) for task in tasks])
    message = f"⏰ *Срочные задачи (дедлайн сегодня/завтра):*\n\n{tasks_text}"
    
    await update.message.reply_text(
        message,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

async def show_tasks_for_completion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать задачи для завершения с inline кнопками"""
    user_id = update.effective_user.id
    tasks = db.get_tasks(user_id, done=False)
    
    if not tasks:
        await update.message.reply_text(
            "🎉 У вас нет активных задач для завершения!",
            reply_markup=get_main_keyboard()
        )
        return
    
    keyboard = get_tasks_keyboard(tasks)
    await update.message.reply_text(
        "✅ Выберите задачу для отметки о выполнении:",
        reply_markup=keyboard
    )

async def handle_task_completion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия на кнопку завершения задачи"""
    query = update.callback_query
    await query.answer()
    
    task_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    
    success = db.mark_task_done(task_id, user_id)
    
    if success:
        # edit the inline message (no ReplyKeyboardMarkup allowed here)
        await query.edit_message_text("✅ Задача отмечена как выполненная!")
        await query.message.reply_text("✅ Задача отмечена как выполненная!", reply_markup=get_main_keyboard())
    else:
        await query.edit_message_text("❌ Ошибка при обновлении задачи")
        await query.message.reply_text("❌ Ошибка при обновлении задачи", reply_markup=get_main_keyboard())


async def start_show_description_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /desc <id|name> - показать подробное описание задачи.
    Если аргументы не переданы, переводим в состояние ожидания ввода запроса."""
    args = context.args
    if args:
        query = " ".join(args)
        # try interpret as id
        if query.isdigit():
            task = db.get_task_by_id(int(query), update.effective_user.id)
        else:
            task = db.get_task_by_name(update.effective_user.id, query)

        if not task:
            await update.message.reply_text("❌ Задача не найдена. Проверьте id или название.")
            return ConversationHandler.END

        desc = task.get('description') or "(Описание отсутствует)"
        await update.message.reply_text(f"*{task['task']}*\n\n{desc}", parse_mode='Markdown')
        return ConversationHandler.END

    # no args -> ask user to send id or name
    await update.message.reply_text("Введите id задачи или её название:")
    return DESC_QUERY


async def wait_for_desc_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if query.isdigit():
        task = db.get_task_by_id(int(query), update.effective_user.id)
    else:
        task = db.get_task_by_name(update.effective_user.id, query)

    if not task:
        await update.message.reply_text("❌ Задача не найдена.")
        return ConversationHandler.END

    desc = task.get('description') or "(Описание отсутствует)"
    await update.message.reply_text(f"*{task['task']}*\n\n{desc}", parse_mode='Markdown')
    return ConversationHandler.END


async def start_edit_description_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /editdesc <id|name> - начать редактирование описания задачи.
    Если аргументы не заданы — спросим пользователя, какую задачу редактировать."""
    args = context.args
    if args:
        query = " ".join(args)
        if query.isdigit():
            task = db.get_task_by_id(int(query), update.effective_user.id)
        else:
            task = db.get_task_by_name(update.effective_user.id, query)

        if not task:
            await update.message.reply_text("❌ Задача не найдена. Проверьте id или название.")
            return ConversationHandler.END

        # store task id in user_data and ask for new description
        context.user_data['edit_task_id'] = task['id']
        await update.message.reply_text(f"Введите новое подробное описание для задачи '*{task['task']}*':", parse_mode='Markdown')
        return EDIT_TEXT

    # ask which task to edit
    await update.message.reply_text("Введите id задачи или её название, для которой хотите изменить описание:")
    return EDIT_SELECT


async def receive_task_for_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if query.isdigit():
        task = db.get_task_by_id(int(query), update.effective_user.id)
    else:
        task = db.get_task_by_name(update.effective_user.id, query)

    if not task:
        await update.message.reply_text("❌ Задача не найдена.")
        return ConversationHandler.END

    context.user_data['edit_task_id'] = task['id']
    await update.message.reply_text(f"Введите новое подробное описание для задачи '*{task['task']}*':", parse_mode='Markdown')
    return EDIT_TEXT


async def receive_new_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_desc = update.message.text.strip()
    task_id = context.user_data.get('edit_task_id')
    user_id = update.effective_user.id

    if not task_id:
        await update.message.reply_text("❌ Внутренняя ошибка: не указан id задачи.")
        return ConversationHandler.END

    success = db.update_task_description(task_id, user_id, new_desc)
    context.user_data.pop('edit_task_id', None)

    if success:
        await update.message.reply_text("✅ Описание успешно обновлено.", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("❌ Ошибка при обновлении описания.", reply_markup=get_main_keyboard())

    return ConversationHandler.END


def get_description_conversation():
    from telegram.ext import CommandHandler, MessageHandler
    return ConversationHandler(
        entry_points=[
            CommandHandler('desc', start_show_description_command),
            MessageHandler(filters.Regex('^(🔎 Описание)$'), start_show_description_command)
        ],
        states={
            DESC_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_for_desc_query)]
        },
        fallbacks=[MessageHandler(filters.Regex('^(Отмена|/cancel)$'), lambda u, c: ConversationHandler.END)]
    )


def get_edit_description_conversation():
    from telegram.ext import CommandHandler, MessageHandler
    return ConversationHandler(
        entry_points=[
            CommandHandler('editdesc', start_edit_description_command),
            MessageHandler(filters.Regex('^(✏️ Редактировать описание)$'), start_edit_description_command)
        ],
        states={
            EDIT_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_for_edit)],
            EDIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_description)]
        },
        fallbacks=[MessageHandler(filters.Regex('^(Отмена|/cancel)$'), lambda u, c: ConversationHandler.END)]
    )


async def start_general_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало общего редактирования задачи: /edittask <id|name> или кнопка
    Если аргументы заданы — сразу переходим к выбору поля, иначе просим id/имя"""
    args = context.args
    if args:
        query = " ".join(args)
        if query.isdigit():
            task = db.get_task_by_id(int(query), update.effective_user.id)
        else:
            task = db.get_task_by_name(update.effective_user.id, query)

        if not task:
            await update.message.reply_text("❌ Задача не найдена. Проверьте id или название.")
            return ConversationHandler.END

        context.user_data['edit_task_id'] = task['id']
        # show current values and ask which field to edit
        await update.message.reply_text(
            f"Редактирование задачи *{task['task']}* (id: {task['id']})\n\n"
            f"Приоритет: {task.get('priority')}\nДедлайн: {task.get('deadline')}\nОписание: {task.get('description') or '(отсутствует)'}\n\n"
            "Выберите поле для редактирования:",
            reply_markup=get_edit_fields_keyboard(),
            parse_mode='Markdown'
        )
        return EDIT_FIELD_SELECT

    await update.message.reply_text("Введите id задачи или её название для редактирования:")
    return EDIT_TASK_SELECT


async def receive_task_for_general_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if query.isdigit():
        task = db.get_task_by_id(int(query), update.effective_user.id)
    else:
        task = db.get_task_by_name(update.effective_user.id, query)

    if not task:
        await update.message.reply_text("❌ Задача не найдена.")
        return ConversationHandler.END

    context.user_data['edit_task_id'] = task['id']
    await update.message.reply_text(
        f"Редактирование задачи *{task['task']}* (id: {task['id']})\n\n"
        f"Приоритет: {task.get('priority')}\nДедлайн: {task.get('deadline')}\nОписание: {task.get('description') or '(отсутствует)'}\n\n"
        "Выберите поле для редактирования:",
        reply_markup=get_edit_fields_keyboard(),
        parse_mode='Markdown'
    )
    return EDIT_FIELD_SELECT


async def receive_field_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text.strip()
    if choice == 'Отмена':
        await update.message.reply_text("❌ Редактирование отменено.", reply_markup=get_main_keyboard())
        context.user_data.pop('edit_task_id', None)
        return ConversationHandler.END

    if choice == 'Завершить редактирование':
        await update.message.reply_text("✅ Редактирование завершено.", reply_markup=get_main_keyboard())
        context.user_data.pop('edit_task_id', None)
        return ConversationHandler.END

    task_id = context.user_data.get('edit_task_id')
    if not task_id:
        await update.message.reply_text("❌ Внутренняя ошибка: не задана задача.")
        return ConversationHandler.END

    # For priority show priority keyboard
    if choice == 'Приоритет':
        context.user_data['field_to_edit'] = 'priority'
        await update.message.reply_text("Выберите новый приоритет:", reply_markup=get_priority_keyboard())
        return EDIT_FIELD_VALUE

    # For mark done handle immediately
    if choice == 'Отметить выполненной':
        success = update_note(task_id, update.effective_user.id, {'is_done': True})
        if success:
            await update.message.reply_text("✅ Задача отмечена как выполненная.", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text("❌ Не удалось обновить задачу.", reply_markup=get_main_keyboard())
        context.user_data.pop('edit_task_id', None)
        return ConversationHandler.END

    # For other fields ask for new value
    field_map = {
        'Заголовок': 'task',
        'Дедлайн': 'deadline',
        'Описание': 'description'
    }

    if choice in field_map:
        context.user_data['field_to_edit'] = field_map[choice]
        await update.message.reply_text(f"Введите новое значение для поля '{choice}':")
        return EDIT_FIELD_VALUE

    # Unknown option
    await update.message.reply_text("Неизвестная опция. Попробуйте снова.")
    return EDIT_FIELD_SELECT


async def receive_new_field_value_general(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_value = update.message.text.strip()
    task_id = context.user_data.get('edit_task_id')
    field = context.user_data.get('field_to_edit')
    user_id = update.effective_user.id

    if not task_id or not field:
        await update.message.reply_text("❌ Внутренняя ошибка. Попробуйте снова.")
        context.user_data.pop('field_to_edit', None)
        return ConversationHandler.END

    # validate deadline format
    if field == 'deadline':
        if new_value == '-' or new_value.lower() in ('none', 'null'):
            val = None
        else:
            try:
                datetime.strptime(new_value, '%Y-%m-%d')
                val = new_value
            except ValueError:
                await update.message.reply_text("❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД или введите '-' для очистки.")
                return EDIT_FIELD_VALUE
    else:
        val = new_value

    success = update_note(task_id, user_id, {field: val})
    context.user_data.pop('field_to_edit', None)

    if success:
        # fetch updated task and show brief summary, then let user continue editing
        task = db.get_task_by_id(task_id, user_id)
        await update.message.reply_text(
            f"✅ Поле обновлено. Текущие значения:\n*{task['task']}*\nПриоритет: {task.get('priority')}\nДедлайн: {task.get('deadline')}\nОписание: {task.get('description') or '(отсутствует)'}\n\n"
            "Выберите следующее поле для редактирования или 'Завершить редактирование'.",
            reply_markup=get_edit_fields_keyboard(),
            parse_mode='Markdown'
        )
        return EDIT_FIELD_SELECT
    else:
        await update.message.reply_text("❌ Ошибка при обновлении. Попробуйте снова или отмените.")
        return EDIT_FIELD_SELECT


def get_general_edit_conversation():
    from telegram.ext import CommandHandler
    return ConversationHandler(
        entry_points=[
            CommandHandler('edittask', start_general_edit),
            MessageHandler(filters.Regex('^(✏️ Редактировать задачу)$'), start_general_edit)
        ],
        states={
            EDIT_TASK_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task_for_general_edit)],
            EDIT_FIELD_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_field_choice)],
            EDIT_FIELD_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_field_value_general)]
        },
        fallbacks=[MessageHandler(filters.Regex('^(Отмена|/cancel)$'), lambda u, c: ConversationHandler.END)]
    )


async def show_completed_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать список выполненных задач пользователя для возможного восстановления"""
    user_id = update.effective_user.id
    # get tasks marked done
    tasks = db.get_tasks(user_id, done=True)

    if not tasks:
        await update.message.reply_text(
            "✅ У вас нет выполненных задач для восстановления!",
            reply_markup=get_main_keyboard()
        )
        return

    keyboard = get_completed_tasks_keyboard(tasks)
    await update.message.reply_text(
        "♻️ Выберите задачу для восстановления:",
        reply_markup=keyboard
    )


async def handle_task_restore(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия на кнопку восстановления задачи"""
    query = update.callback_query
    await query.answer()

    task_id = int(query.data.split('_')[1])
    user_id = query.from_user.id

    success = db.restore_task(task_id, user_id)

    if success:
        # edit the inline message (no ReplyKeyboardMarkup allowed here)
        await query.edit_message_text("✅ Задача успешно восстановлена!")
        # send a new message with the main (reply) keyboard
        await query.message.reply_text("✅ Задача успешно восстановлена!", reply_markup=get_main_keyboard())
    else:
        await query.edit_message_text("❌ Ошибка при восстановлении задачи")
        await query.message.reply_text("❌ Ошибка при восстановлении задачи", reply_markup=get_main_keyboard())