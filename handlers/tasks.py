from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from database.supabase_client import db
from utils.keyboards import get_tasks_keyboard, get_main_keyboard
from datetime import datetime

# States for description-related conversations
DESC_QUERY, EDIT_SELECT, EDIT_TEXT = range(3)

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
            deadline = datetime.fromisoformat(task['deadline'].replace('Z', '+00:00'))
            deadline_text = f" | ⏰ {deadline.strftime('%d.%m.%Y')}"
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
        await query.edit_message_text(
            "✅ Задача отмечена как выполненная!",
            reply_markup=get_main_keyboard()
        )
    else:
        await query.edit_message_text(
            "❌ Ошибка при обновлении задачи",
            reply_markup=get_main_keyboard()
        )


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