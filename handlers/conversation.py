from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CallbackQueryHandler
from database.supabase_client import db
from utils.keyboards import (
    get_priority_keyboard,
    get_main_keyboard,
    get_cancel_keyboard,
    get_skip_or_cancel_keyboard,
    get_deadline_quick_keyboard,
)
from utils.notes import create_note_from_user_data
from datetime import datetime, timedelta

from telegram_bot_calendar import DetailedTelegramCalendar, LSTEP

# Состояния для ConversationHandler
TASK, DESCRIPTION, PRIORITY, DEADLINE, TIME = range(5)


async def start_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса добавления задачи"""
    await update.message.reply_text(
        "📝 Введите краткий заголовок вашей задачи:",
        reply_markup=get_cancel_keyboard()
    )
    return TASK


async def receive_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение заголовка задачи"""
    text = update.message.text.strip()
    if text == 'Отмена':
        return await cancel_conversation(update, context)

    context.user_data['task'] = text
    await update.message.reply_text(
        "✍️ (Опционально) Введите подробное описание задачи или нажмите 'Пропустить':",
        reply_markup=get_skip_or_cancel_keyboard()
    )
    return DESCRIPTION


async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение подробного описания (опционально)"""
    text = update.message.text.strip()
    if text == 'Отмена':
        return await cancel_conversation(update, context)

    if text == 'Пропустить' or text == '-':
        context.user_data['description'] = None
    else:
        context.user_data['description'] = text

    await update.message.reply_text(
        "🎯 Выберите приоритет задачи:",
        reply_markup=get_priority_keyboard()
    )
    return PRIORITY


async def receive_priority(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение приоритета задачи"""
    priority_map = {
        '🔴 Высокий': 'high',
        '🟡 Средний': 'medium',
        '🟢 Низкий': 'low'
    }

    user_priority = update.message.text
    if user_priority == 'Отмена':
        return await cancel_conversation(update, context)

    context.user_data['priority'] = priority_map.get(user_priority, 'medium')

    await update.message.reply_text(
        "📅 Выберите удобный вариант дедлайна или 'Выбрать дату':",
        reply_markup=get_deadline_quick_keyboard()
    )
    return DEADLINE


async def receive_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение дедлайна и сохранение задачи. Поддерживает быстрые варианты."""
    user_input = update.message.text.strip()

    if user_input == 'Отмена':
        return await cancel_conversation(update, context)

    deadline = None

    if user_input in ('Пропустить', '-', 'Пропустить '):
        deadline = None
    elif user_input == 'Сегодня':
        deadline = datetime.now().date().isoformat()
    elif user_input == 'Завтра':
        deadline = (datetime.now().date() + timedelta(days=1)).isoformat()
    elif user_input == 'Через 3 дня':
        deadline = (datetime.now().date() + timedelta(days=3)).isoformat()
    elif user_input == 'Выбрать дату':
        # open an inline calendar (python-telegram-calendar is required)
        cal = DetailedTelegramCalendar(min_date=datetime.now().date())
        try:
            markup, step = cal.build()
        except Exception:
            # older/newer API: try create_calendar
            markup = cal.create_calendar()
        # show inline calendar and a simple reply keyboard with only 'Отмена'
        await update.message.reply_text("Выберите дату:", reply_markup=markup)
        await update.message.reply_text("При необходимости отмены нажмите 'Отмена'", reply_markup=get_cancel_keyboard())
        # stay in DEADLINE state; calendar callbacks are handled by CallbackQueryHandler
        return DEADLINE
    else:
        # Попробуем распознать введённую дату
        try:
            datetime.strptime(user_input, '%Y-%m-%d')
            deadline = user_input
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат даты! Используйте ГГГГ-ММ-ДД или выберите быстрый вариант:",
                reply_markup=get_deadline_quick_keyboard()
            )
            return DEADLINE

    # If deadline is provided (date) ask for optional time
    if deadline is not None:
        # store partial date and ask for time
        context.user_data['deadline_date'] = deadline
        await update.message.reply_text(
            "⏱️ (Опционально) Введите время дедлайна в формате ЧЧ:ММ (например, 14:30), или нажмите 'Пропустить' / 'Отмена':",
            reply_markup=get_skip_or_cancel_keyboard()
        )
        return TIME

    # Сохраняем задачу в базу данных (без времени) через общую функцию
    user_id = update.effective_user.id
    # ensure no leftover time
    context.user_data.pop('deadline_time', None)
    task_data = create_note_from_user_data(user_id, context.user_data)

    if task_data:
        # Очищаем временные данные
        context.user_data.clear()

        success_message = "✅ Задача успешно добавлена!"
        if deadline:
            success_message += f"\n📅 Срок выполнения: {deadline}"

        await update.message.reply_text(
            success_message,
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "❌ Ошибка при добавлении задачи",
            reply_markup=get_main_keyboard()
        )

    return ConversationHandler.END


async def receive_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение времени дедлайна и сохранение задачи"""
    user_input = update.message.text.strip()
    if user_input == 'Отмена':
        return await cancel_conversation(update, context)

    date_part = context.user_data.get('deadline_date')

    if user_input in ('Пропустить', '-', 'Пропустить '):
        # user skipped time
        context.user_data['deadline_time'] = None
        deadline_full = date_part
    else:
        # accept HH:MM or full ISO datetime
        try:
            if ':' in user_input and len(user_input.split(':')[0]) <= 2:
                # time only
                hh_mm = user_input
                # validate
                datetime.strptime(hh_mm, '%H:%M')
                # store time in user_data so shared creator can compose final deadline
                context.user_data['deadline_time'] = hh_mm
                deadline_full = f"{date_part}T{hh_mm}:00"
            else:
                # try full datetime
                dt = datetime.fromisoformat(user_input)
                # normalize into date and time parts for consistency
                context.user_data['deadline_date'] = dt.date().isoformat()
                context.user_data['deadline_time'] = dt.strftime('%H:%M')
                deadline_full = dt.isoformat()
        except Exception:
            await update.message.reply_text(
                "❌ Неверный формат времени! Введите в формате ЧЧ:ММ (например, 14:30) или нажмите 'Пропустить'.",
                reply_markup=get_skip_or_cancel_keyboard()
            )
            return TIME

    # Сохраняем задачу через общую функцию (create_note_from_user_data прочитает deadline_date и deadline_time)
    user_id = update.effective_user.id
    task_data = create_note_from_user_data(user_id, context.user_data)

    if task_data:
        context.user_data.clear()
        success_message = "✅ Задача успешно добавлена!"
        if deadline_full:
            success_message += f"\n📅 Срок выполнения: {deadline_full}"
        await update.message.reply_text(success_message, reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("❌ Ошибка при добавлении задачи", reply_markup=get_main_keyboard())

    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена диалога"""
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Добавление задачи отменено",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END


def get_conversation_handler():
    """Создание и возврат ConversationHandler"""
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^(📝 Добавить задачу)$'), start_add_task)],
        states={
            TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_task)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_description)],
            PRIORITY: [MessageHandler(filters.Regex('^(🔴 Высокий|🟡 Средний|🟢 Низкий|Отмена)$'), receive_priority)],
            DEADLINE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_deadline),
                CallbackQueryHandler(handle_calendar_selection)
            ],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time)],
        },
        fallbacks=[MessageHandler(filters.Regex('^(Отмена|/cancel)$'), cancel_conversation)]
    )


async def handle_calendar_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback'а календаря (python-telegram-calendar)
    This handler is used only when DetailedTelegramCalendar is available. It processes the inline
    calendar callbacks, stores selected date into context.user_data['deadline_date'] and moves
    the conversation to TIME state (asks for optional time)."""
    query = update.callback_query
    await query.answer()

    # process calendar callback

    cal = DetailedTelegramCalendar()
    try:
        result, key, step = cal.process(query.data)
    except Exception:
        # older/newer API variants
        try:
            result, key, step = cal.process_callback_data(query.data)
        except Exception:
            await query.edit_message_text("Ошибка календаря. Пожалуйста, введите дату вручную.")
            return DEADLINE

    if not result:
        # still selecting, update inline keyboard
        await query.edit_message_text(f"Выберите {LSTEP[step]}", reply_markup=key)
        return DEADLINE

    # result is a date
    selected_date = result.strftime('%Y-%m-%d')
    context.user_data['deadline_date'] = selected_date

    # confirm selection and ask for time
    await query.edit_message_text(f"Выбрана дата: {selected_date}")
    await query.message.reply_text(
        "⏱️ (Опционально) Введите время дедлайна в формате ЧЧ:ММ (например, 14:30), или нажмите 'Пропустить' / 'Отмена':",
        reply_markup=get_skip_or_cancel_keyboard()
    )
    return TIME