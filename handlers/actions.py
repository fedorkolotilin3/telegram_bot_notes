from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ConversationHandler
from database.supabase_client import db
from utils.keyboards import (
    get_tasks_keyboard, get_main_keyboard, get_edit_fields_keyboard,
    get_priority_keyboard, get_completed_tasks_keyboard, get_skip_or_cancel_keyboard,
    get_cancel_keyboard, get_deadline_quick_keyboard, get_deadline_edit_keyboard
)
from telegram_bot_calendar import DetailedTelegramCalendar, LSTEP
from utils.notes import update_note, create_note_from_user_data
from datetime import datetime
from datetime import time as dt_time
from handlers import states


def _parse_quick_deadline_option(user_input: str):
    """Parse quick deadline options used by both create and edit flows.
    Returns tuple (action, date_str)
    action: 'none' (skip), 'date' (date_str provided), 'calendar' (open calendar), 'invalid'
    """
    from datetime import timedelta
    if user_input in ('Пропустить', '-', 'Пропустить '):
        return 'none', None
    if user_input == 'Сегодня':
        return 'date', datetime.now().date().isoformat()
    if user_input == 'Завтра':
        return 'date', (datetime.now().date() + timedelta(days=1)).isoformat()
    if user_input == 'Через 3 дня':
        return 'date', (datetime.now().date() + timedelta(days=3)).isoformat()
    if user_input == 'Выбрать дату':
        return 'calendar', None
    # try parse YYYY-MM-DD
    try:
        datetime.strptime(user_input, '%Y-%m-%d')
        return 'date', user_input
    except Exception:
        return 'invalid', None


def _parse_time_input(user_input: str):
    """Parse time input. Returns ('time', hh:mm) or ('datetime', iso) or ('invalid', None) or ('skip', None)"""
    if user_input in ('Пропустить', '-', 'Пропустить '):
        return 'skip', None
    # time only HH:MM
    try:
        if ':' in user_input and len(user_input.split(':')[0]) <= 2:
            datetime.strptime(user_input, '%H:%M')
            return 'time', user_input
        # try full ISO datetime
        dt = datetime.fromisoformat(user_input)
        return 'datetime', dt.isoformat()
    except Exception:
        return 'invalid', None


# new helper: build hours keyboard (0..23)
def _build_hours_keyboard(prefix='time'):
    buttons = []
    row = []
    for h in range(24):
        label = f"{h:02d}"
        cb = f"{prefix}_hour_{h}"
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 6:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    # add skip button
    buttons.append([InlineKeyboardButton("Пропустить", callback_data=f"{prefix}_skip"),
                    InlineKeyboardButton("Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)

# new helper: build minutes keyboard for given hour
def _build_minutes_keyboard(hour, prefix='time'):
    minute_options = [0, 15, 30, 45]
    buttons = []
    row = []
    for m in minute_options:
        label = f"{m:02d}"
        cb = f"{prefix}_min_{hour}_{m}"
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 4:
            buttons.append(row)
            row = []
    # back to hours + cancel
    buttons.append([InlineKeyboardButton("Назад (часы)", callback_data=f"{prefix}_hours"),
                    InlineKeyboardButton("Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)

# добавляем форматирование задачи — необходимо для show_my_tasks и др.
def format_task(task):
    task_id = task.get('id') or task.get('task_id') or '?'
    task_text = task.get('task', '')
    priority_emoji = {
        'high': '🔴',
        'medium': '🟡',
        'low': '🟢'
    }.get(task.get('priority'), '⚪')

    deadline_text = ""
    deadline_val = task.get('deadline')
    if deadline_val:
        try:
            # поддерживаем формат с Z и без
            deadline = datetime.fromisoformat(deadline_val.replace('Z', '+00:00'))
            date_part = deadline.strftime('%d.%m.%Y')
            time_part = ''
            if deadline.time() != dt_time(0, 0):
                time_part = f" {deadline.strftime('%H:%M')}"
            deadline_text = f" | ⏰ {date_part}{time_part}"
        except Exception:
            deadline_text = " | ⏰ Неверная дата"

    return f"*{task_id}*. {priority_emoji} {task_text}{deadline_text}"


async def start_add_task(update: Update, context):
    await update.message.reply_text(
        "📝 Введите краткий заголовок вашей задачи:",
        reply_markup=get_cancel_keyboard()
    )
    return states.TASK


async def receive_task(update: Update, context):
    text = update.message.text.strip()
    if text == 'Отмена':
        return await cancel_conversation(update, context)

    context.user_data['task'] = text
    await update.message.reply_text(
        "✍️ (Опционально) Введите подробное описание задачи или нажмите 'Пропустить':",
        reply_markup=get_skip_or_cancel_keyboard()
    )
    return states.DESCRIPTION


async def receive_description(update: Update, context):
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
    return states.PRIORITY


async def receive_priority(update: Update, context):
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
    return states.DEADLINE


async def receive_deadline(update: Update, context):
    user_input = update.message.text.strip()

    if user_input == 'Отмена':
        return await cancel_conversation(update, context)

    # Use local parsing helper
    action, date_val = _parse_quick_deadline_option(user_input)

    if action == 'invalid':
        await update.message.reply_text(
            "❌ Неверный формат даты! Используйте ГГГГ-ММ-ДД или выберите быстрый вариант:",
            reply_markup=get_deadline_quick_keyboard()
        )
        return states.DEADLINE

    if action == 'calendar':
        cal = DetailedTelegramCalendar(min_date=datetime.now().date())
        try:
            markup, step = cal.build()
        except Exception:
            markup = cal.create_calendar()
        await update.message.reply_text("Выберите дату:", reply_markup=markup)
        await update.message.reply_text("При необходимости отмены нажмите 'Отмена'", reply_markup=get_cancel_keyboard())
        return states.DEADLINE

    if action == 'none':
        user_id = update.effective_user.id
        context.user_data.pop('deadline_time', None)
        # If editing an existing task, update instead of creating
        edit_task_id = context.user_data.get('edit_task_id')
        if edit_task_id:
            success = update_note(edit_task_id, user_id, {'deadline': None})
            context.user_data.pop('edit_task_id', None)
            context.user_data.pop('field_to_edit', None)
            if success:
                await update.message.reply_text("✅ Дедлайн успешно удалён.", reply_markup=get_main_keyboard())
            else:
                await update.message.reply_text("❌ Ошибка при обновлении дедлайна", reply_markup=get_main_keyboard())
            return ConversationHandler.END

        task_data = create_note_from_user_data(user_id, context.user_data)

        if task_data:
            context.user_data.clear()
            await update.message.reply_text("✅ Задача успешно добавлена!", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text("❌ Ошибка при добавлении задачи", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    # при выборе даты показываем inline time-picker (часы)
    context.user_data['deadline_date'] = date_val
    await update.message.reply_text("Выберите время дедлайна (час):", reply_markup=_build_hours_keyboard())
    return states.TIME


async def receive_time(update: Update, context):
    user_input = update.message.text.strip()
    if user_input == 'Отмена':
        return await cancel_conversation(update, context)

    date_part = context.user_data.get('deadline_date')

    if user_input in ('Пропустить', '-', 'Пропустить '):
        context.user_data['deadline_time'] = None
        deadline_full = date_part
    else:
        try:
            if ':' in user_input and len(user_input.split(':')[0]) <= 2:
                hh_mm = user_input
                datetime.strptime(hh_mm, '%H:%M')
                context.user_data['deadline_time'] = hh_mm
                deadline_full = f"{date_part}T{hh_mm}:00"
            else:
                dt = datetime.fromisoformat(user_input)
                context.user_data['deadline_date'] = dt.date().isoformat()
                context.user_data['deadline_time'] = dt.strftime('%H:%M')
                deadline_full = dt.isoformat()
        except Exception:
            await update.message.reply_text(
                "❌ Неверный формат времени! Введите в формате ЧЧ:ММ (например, 14:30) или нажмите 'Пропустить'.",
                reply_markup=get_skip_or_cancel_keyboard()
            )
            return states.TIME

    user_id = update.effective_user.id
    edit_task_id = context.user_data.get('edit_task_id')

    if edit_task_id:
        # prepare fields for update_note
        fields = {}
        # use stored date/time parts
        date_part = context.user_data.get('deadline_date')
        time_part = context.user_data.get('deadline_time')
        if date_part is not None:
            fields['deadline_date'] = date_part
        if time_part is not None:
            fields['deadline_time'] = time_part
        success = update_note(edit_task_id, user_id, fields)
        # clean up edit context
        context.user_data.pop('edit_task_id', None)
        context.user_data.pop('field_to_edit', None)
        context.user_data.pop('deadline_date', None)
        context.user_data.pop('deadline_time', None)
        if success:
            await update.message.reply_text(f"✅ Дедлайн обновлён: {deadline_full}", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text("❌ Ошибка при обновлении дедлайна", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    # create new task flow
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


async def cancel_conversation(update: Update, context):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Добавление задачи отменено",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END


async def handle_calendar_selection(update: Update, context):
    query = update.callback_query
    await query.answer()

    cal = DetailedTelegramCalendar()
    try:
        result, key, step = cal.process(query.data)
    except Exception:
        try:
            result, key, step = cal.process_callback_data(query.data)
        except Exception:
            await query.edit_message_text("Ошибка календаря. Пожалуйста, введите дату вручную.")
            # если мы редактируем задачу, продолжить в состоянии редактирования поля
            if context.user_data.get('edit_task_id'):
                return states.EDIT_FIELD_VALUE
            return states.DEADLINE

    if not result:
        await query.edit_message_text(f"Выберите {LSTEP[step]}", reply_markup=key)
        # при редактировании остаёмся в EDIT_FIELD_VALUE, иначе в DEADLINE
        if context.user_data.get('edit_task_id'):
            return states.EDIT_FIELD_VALUE
        return states.DEADLINE

    selected_date = result.strftime('%Y-%m-%d')
    context.user_data['deadline_date'] = selected_date

    await query.edit_message_text(f"Выбрана дата: {selected_date}")
    # show inline time picker instead of text prompt
    await query.message.reply_text("Выберите время дедлайна (час):", reply_markup=_build_hours_keyboard())
    if context.user_data.get('edit_task_id'):
        return states.EDIT_FIELD_VALUE
    return states.TIME


# new handler: process time pick callbacks (hours/minutes/skip)
async def handle_time_selection(update: Update, context):
    query = update.callback_query
    await query.answer()
    data = query.data  # e.g. "time_hour_14" or "time_min_14_30" or "time_skip" or "time_hours"
    user_id = query.from_user.id
    edit_task_id = context.user_data.get('edit_task_id')

    if data.endswith("_hours") or data == "time_hours":
        # show hours keyboard
        await query.edit_message_text("Выберите час:", reply_markup=_build_hours_keyboard())
        return ConversationHandler.END if not edit_task_id and False else states.EDIT_FIELD_VALUE if edit_task_id else states.TIME

    if data.endswith("_skip") or data == "time_skip":
        # skip choosing minutes -> set no time
        date_part = context.user_data.get('deadline_date')
        if edit_task_id:
            # update only date part
            success = update_note(edit_task_id, user_id, {'deadline_date': date_part})
            context.user_data.pop('field_to_edit', None)
            context.user_data.pop('edit_task_id', None)
            context.user_data.pop('deadline_date', None)
            context.user_data.pop('deadline_time', None)
            if success:
                await query.message.reply_text("✅ Дедлайн обновлён (время не задано).", reply_markup=get_main_keyboard())
            else:
                await query.message.reply_text("❌ Ошибка при обновлении дедлайна", reply_markup=get_main_keyboard())
            return ConversationHandler.END
        # creating new task: create with date only
        task_data = create_note_from_user_data(user_id, context.user_data)
        if task_data:
            context.user_data.clear()
            await query.message.reply_text("✅ Задача успешно добавлена!", reply_markup=get_main_keyboard())
        else:
            await query.message.reply_text("❌ Ошибка при добавлении задачи", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    # hour selection: pattern like "*_hour_{H}" (support both 'time_hour_' and any prefix)
    if "_hour_" in data:
        try:
            parts = data.split('_')
            hour = int(parts[-1])
        except Exception:
            await query.message.reply_text("Ошибка выбора часа. Попробуйте ещё раз.")
            return ConversationHandler.END
        # show minutes keyboard for selected hour
        await query.edit_message_text(f"Выбран час {hour:02d}. Выберите минуты:", reply_markup=_build_minutes_keyboard(hour))
        # stay in appropriate state
        return states.EDIT_FIELD_VALUE if edit_task_id else states.TIME

    # minute selection: pattern "*_min_{H}_{M}"
    if "_min_" in data:
        try:
            parts = data.split('_')
            hour = int(parts[-2])
            minute = int(parts[-1])
        except Exception:
            await query.message.reply_text("Ошибка выбора минут. Попробуйте ещё раз.")
            return ConversationHandler.END

        hh_mm = f"{hour:02d}:{minute:02d}"
        # store
        context.user_data['deadline_time'] = hh_mm
        # build full representation if date exists
        date_part = context.user_data.get('deadline_date')
        if date_part:
            deadline_full = f"{date_part}T{hh_mm}:00"
        else:
            deadline_full = hh_mm

        if edit_task_id:
            # update existing task with date/time parts
            fields = {}
            if context.user_data.get('deadline_date') is not None:
                fields['deadline_date'] = context.user_data.get('deadline_date')
            fields['deadline_time'] = hh_mm
            success = update_note(edit_task_id, user_id, fields)
            # cleanup
            context.user_data.pop('edit_task_id', None)
            context.user_data.pop('field_to_edit', None)
            context.user_data.pop('deadline_date', None)
            context.user_data.pop('deadline_time', None)
            if success:
                await query.message.reply_text(f"✅ Дедлайн обновлён: {deadline_full}", reply_markup=get_main_keyboard())
            else:
                await query.message.reply_text("❌ Ошибка при обновлении дедлайна", reply_markup=get_main_keyboard())
            return ConversationHandler.END

        # create new task flow
        task_data = create_note_from_user_data(user_id, context.user_data)
        if task_data:
            context.user_data.clear()
            success_message = "✅ Задача успешно добавлена!"
            if deadline_full:
                success_message += f"\n📅 Срок выполнения: {deadline_full}"
            await query.message.reply_text(success_message, reply_markup=get_main_keyboard())
        else:
            await query.message.reply_text("❌ Ошибка при добавлении задачи", reply_markup=get_main_keyboard())
        return ConversationHandler.END

    # unknown callback -> ignore
    await query.answer()
    return ConversationHandler.END


async def show_my_tasks(update: Update, context):
    user_id = update.effective_user.id
    tasks = db.get_tasks(user_id, done=False)
    if not tasks:
        await update.message.reply_text("🎉 У вас нет активных задач!", reply_markup=get_main_keyboard())
        return
    tasks_text = "\n".join([format_task(task) for task in tasks])
    message = f"📋 *Ваши активные задачи:*\n\n{tasks_text}"
    await update.message.reply_text(message, reply_markup=get_main_keyboard(), parse_mode='Markdown')


async def show_important_tasks(update: Update, context):
    user_id = update.effective_user.id
    tasks = db.get_priority_tasks(user_id, "high")
    if not tasks:
        await update.message.reply_text("✅ Нет задач с высоким приоритетом!", reply_markup=get_main_keyboard())
        return
    tasks_text = "\n".join([format_task(task) for task in tasks])
    message = f"🔴 *Задачи с высоким приоритетом:*\n\n{tasks_text}"
    await update.message.reply_text(message, reply_markup=get_main_keyboard(), parse_mode='Markdown')


async def show_urgent_tasks(update: Update, context):
    user_id = update.effective_user.id
    tasks = db.get_urgent_tasks(user_id)
    if not tasks:
        await update.message.reply_text("✅ Нет срочных задач на ближайшие дни!", reply_markup=get_main_keyboard())
        return
    tasks_text = "\n".join([format_task(task) for task in tasks])
    message = f"⏰ *Срочные задачи (дедлайн сегодня/завтра):*\n\n{tasks_text}"
    await update.message.reply_text(message, reply_markup=get_main_keyboard(), parse_mode='Markdown')


async def show_tasks_for_completion(update: Update, context):
    user_id = update.effective_user.id
    tasks = db.get_tasks(user_id, done=False)
    if not tasks:
        await update.message.reply_text("🎉 У вас нет активных задач для завершения!", reply_markup=get_main_keyboard())
        return
    keyboard = get_tasks_keyboard(tasks)
    await update.message.reply_text("✅ Выберите задачу для отметки о выполнении:", reply_markup=keyboard)


async def handle_task_completion(update: Update, context):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    success = db.mark_task_done(task_id, user_id)
    if success:
        await query.message.reply_text("✅ Задача отмечена как выполненная!", reply_markup=get_main_keyboard())
    else:
        await query.message.reply_text("❌ Ошибка при обновлении задачи", reply_markup=get_main_keyboard())


async def start_show_description_command(update: Update, context):
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
        desc = task.get('description') or "(Описание отсутствует)"
        await update.message.reply_text(f"*{task['task']}*\n\n{desc}", parse_mode='Markdown')
        return ConversationHandler.END
    await update.message.reply_text("Введите id задачи или её название:")
    return states.DESC_QUERY


async def wait_for_desc_query(update: Update, context):
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


async def start_edit_description_command(update: Update, context):
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
        await update.message.reply_text(f"Введите новое подробное описание для задачи '*{task['task']}*':", parse_mode='Markdown')
        return states.EDIT_TEXT
    await update.message.reply_text("Введите id задачи или её название, для которой хотите изменить описание:")
    return states.EDIT_SELECT


async def receive_task_for_edit(update: Update, context):
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
    return states.EDIT_TEXT


async def receive_new_description(update: Update, context):
    new_desc = update.message.text.strip()
    task_id = context.user_data.get('edit_task_id')
    user_id = update.effective_user.id
    if not task_id:
        await update.message.reply_text("❌ Внутренняя ошибка: не указан id задачи.")
        return ConversationHandler.END
    success = update_note(task_id, user_id, {'description': new_desc})
    context.user_data.pop('edit_task_id', None)
    if success:
        await update.message.reply_text("✅ Описание успешно обновлено.", reply_markup=get_main_keyboard())
    else:
        await update.message.reply_text("❌ Ошибка при обновлении описания.", reply_markup=get_main_keyboard())
    return ConversationHandler.END


async def start_general_edit(update: Update, context):
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
        await update.message.reply_text(
            f"Редактирование задачи *{task['task']}* (id: {task['id']})\n\n"
            f"Приоритет: {task.get('priority')}\nДедлайн: {task.get('deadline')}\nОписание: {task.get('description') or '(отсутствует)'}\n\n"
            "Выберите поле для редактирования:",
            reply_markup=get_edit_fields_keyboard(),
            parse_mode='Markdown'
        )
        return states.EDIT_FIELD_SELECT
    await update.message.reply_text("Введите id задачи или её название для редактирования:")
    return states.EDIT_TASK_SELECT


async def receive_task_for_general_edit(update: Update, context):
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
    return states.EDIT_FIELD_SELECT


async def receive_field_choice(update: Update, context):
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

    if choice == 'Приоритет':
        context.user_data['field_to_edit'] = 'priority'
        await update.message.reply_text("Выберите новый приоритет:", reply_markup=get_priority_keyboard())
        return states.EDIT_FIELD_VALUE

    if choice == 'Отметить выполненной':
        success = update_note(task_id, update.effective_user.id, {'is_done': True})
        if success:
            await update.message.reply_text("✅ Задача отмечена как выполненная.", reply_markup=get_main_keyboard())
        else:
            await update.message.reply_text("❌ Не удалось обновить задачу.", reply_markup=get_main_keyboard())
        context.user_data.pop('edit_task_id', None)
        return ConversationHandler.END

    field_map = {
        'Заголовок': 'task',
        'Дедлайн': 'deadline',
        'Описание': 'description'
    }
    if choice in field_map:
        field = field_map[choice]
        context.user_data['field_to_edit'] = field
        if field == 'deadline':
            edit_task_id = context.user_data.get('edit_task_id')
            if edit_task_id:
                # при редактировании — проверяем, есть ли текущий дедлайн
                task = db.get_task_by_id(edit_task_id, update.effective_user.id)
                if task and task.get('deadline'):
                    # если дедлайн есть — даём выбор: изменить дату или время или удалить
                    await update.message.reply_text(
                        "Выберите действие с дедлайном:",
                        reply_markup=get_deadline_edit_keyboard()
                    )
                    return states.EDIT_FIELD_VALUE
            # иначе (создание или редактирование без существующего дедлайна) — предложим только выбрать дату / пропустить
            await update.message.reply_text(
                "📅 Выберите дату дедлайна или пропустите:",
                reply_markup=get_deadline_quick_keyboard()
            )
        elif field == 'description':
            await update.message.reply_text(f"Введите новое подробное описание для задачи:", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"Введите новое значение для поля '{choice}':")
        return states.EDIT_FIELD_VALUE

    await update.message.reply_text("Неизвестная опция. Попробуйте снова.")
    return states.EDIT_FIELD_SELECT


async def receive_new_field_value_general(update: Update, context):
    new_value = update.message.text.strip()
    task_id = context.user_data.get('edit_task_id')
    field = context.user_data.get('field_to_edit')
    user_id = update.effective_user.id
    if not task_id or not field:
        await update.message.reply_text("❌ Внутренняя ошибка. Попробуйте снова.")
        context.user_data.pop('field_to_edit', None)
        return ConversationHandler.END

    if field == 'deadline':
        # special text options when editing existing deadline
        if new_value == 'Изменить время':
            # ensure we have existing date from task
            task = db.get_task_by_id(task_id, user_id)
            if not task or not task.get('deadline'):
                await update.message.reply_text("❌ У задачи нет установленного дедлайна. Сначала выберите дату.", reply_markup=get_deadline_quick_keyboard())
                return states.EDIT_FIELD_VALUE
            # parse existing date part and set into context to allow time selection
            try:
                existing_deadline = task['deadline']
                # try parse ISO, keep date only
                dt = datetime.fromisoformat(existing_deadline.replace('Z', '+00:00'))
                context.user_data['deadline_date'] = dt.date().isoformat()
            except Exception:
                await update.message.reply_text("❌ Не удалось прочитать текущую дату дедлайна. Выберите дату заново.", reply_markup=get_deadline_quick_keyboard())
                return states.EDIT_FIELD_VALUE
            # open time picker (hours)
            await update.message.reply_text("Выберите время дедлайна (час):", reply_markup=_build_hours_keyboard())
            return states.EDIT_FIELD_VALUE

        if new_value == 'Изменить дату':
            # open calendar to pick new date
            cal = DetailedTelegramCalendar(min_date=datetime.now().date())
            try:
                markup, step = cal.build()
            except Exception:
                markup = cal.create_calendar()
            await update.message.reply_text("Выберите дату:", reply_markup=markup)
            await update.message.reply_text("При необходимости отмены нажмите 'Отмена'", reply_markup=get_cancel_keyboard())
            return states.EDIT_FIELD_VALUE

        if new_value in ('Удалить дедлайн', 'Очистить дедлайн'):
            success = update_note(task_id, user_id, {'deadline': None})
            context.user_data.pop('field_to_edit', None)
            context.user_data.pop('edit_task_id', None)
            if success:
                task = db.get_task_by_id(task_id, user_id)
                await update.message.reply_text(
                    f"✅ Дедлайн удалён. Текущие значения:\n*{task['task']}*\nПриоритет: {task.get('priority')}\nДедлайн: {task.get('deadline')}\nОписание: {task.get('description') or '(отсутствует)'}\n\n",
                    reply_markup=get_edit_fields_keyboard(),
                    parse_mode='Markdown'
                )
                return states.EDIT_FIELD_SELECT
            else:
                await update.message.reply_text("❌ Ошибка при удалении дедлайна.")
                return states.EDIT_FIELD_VALUE

        # If we already have a deadline_date stored (either from calendar selection or from pulling existing task),
        # interpret this input as time part (text HH:MM) OR accept quick date selection
        if context.user_data.get('deadline_date'):
            kind, val = _parse_time_input(new_value)
            if kind == 'invalid':
                await update.message.reply_text("❌ Неверный формат времени! Введите в формате ЧЧ:ММ или воспользуйтесь выбором времени.", reply_markup=get_skip_or_cancel_keyboard())
                return states.EDIT_FIELD_VALUE
            if kind == 'skip':
                date_part = context.user_data.pop('deadline_date', None)
                success = update_note(task_id, user_id, {'deadline_date': date_part})
                context.user_data.pop('field_to_edit', None)
                # keep edit_task_id to allow further edits
                if success:
                    task = db.get_task_by_id(task_id, user_id)
                    await update.message.reply_text(
                        f"✅ Дедлайн обновлён. Текущие значения:\n*{task['task']}*\nПриоритет: {task.get('priority')}\nДедлайн: {task.get('deadline')}\nОписание: {task.get('description') or '(отсутствует)'}\n\n",
                        reply_markup=get_edit_fields_keyboard(),
                        parse_mode='Markdown'
                    )
                    return states.EDIT_FIELD_SELECT
                else:
                    await update.message.reply_text("❌ Ошибка при обновлении дедлайна.")
                    return states.EDIT_FIELD_VALUE
            if kind == 'time':
                hh_mm = val
                date_part = context.user_data.pop('deadline_date', None)
                success = update_note(task_id, user_id, {'deadline_date': date_part, 'deadline_time': hh_mm})
                context.user_data.pop('field_to_edit', None)
                if success:
                    task = db.get_task_by_id(task_id, user_id)
                    await update.message.reply_text(
                        f"✅ Дедлайн обновлён. Текущие значения:\n*{task['task']}*\nПриоритет: {task.get('priority')}\nДедлайн: {task.get('deadline')}\nОписание: {task.get('description') or '(отсутствует)'}\n\n",
                        reply_markup=get_edit_fields_keyboard(),
                        parse_mode='Markdown'
                    )
                    return states.EDIT_FIELD_SELECT
                else:
                    await update.message.reply_text("❌ Ошибка при обновлении дедлайна.")
                    return states.EDIT_FIELD_VALUE
            if kind == 'datetime':
                success = update_note(task_id, user_id, {'deadline': val})
                context.user_data.pop('field_to_edit', None)
                if success:
                    task = db.get_task_by_id(task_id, user_id)
                    await update.message.reply_text(
                        f"✅ Дедлайн обновлён. Текущие значения:\n*{task['task']}*\nПриоритет: {task.get('priority')}\nДедлайн: {task.get('deadline')}\nОписание: {task.get('description') or '(отсутствует)'}\n\n",
                        reply_markup=get_edit_fields_keyboard(),
                        parse_mode='Markdown'
                    )
                    return states.EDIT_FIELD_SELECT
                else:
                    await update.message.reply_text("❌ Ошибка при обновлении дедлайна.")
                    return states.EDIT_FIELD_VALUE

        # otherwise interpret this input as a quick option/date selection (only 'Выбрать дату' or 'Пропустить' expected)
        action, date_val = _parse_quick_deadline_option(new_value)
        if action == 'invalid':
            await update.message.reply_text("❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД или введите '-' для очистки.")
            return states.EDIT_FIELD_VALUE
        if action == 'calendar':
            cal = DetailedTelegramCalendar(min_date=datetime.now().date())
            try:
                markup, step = cal.build()
            except Exception:
                markup = cal.create_calendar()
            await update.message.reply_text("Выберите дату:", reply_markup=markup)
            await update.message.reply_text("При необходимости отмены нажмите 'Отмена'", reply_markup=get_cancel_keyboard())
            return states.EDIT_FIELD_VALUE
        if action == 'none':
            # explicit clear of deadline
            success = update_note(task_id, user_id, {'deadline': None})
            context.user_data.pop('field_to_edit', None)
            if success:
                task = db.get_task_by_id(task_id, user_id)
                await update.message.reply_text(
                    f"✅ Дедлайн обновлён. Текущие значения:\n*{task['task']}*\nПриоритет: {task.get('priority')}\nДедлайн: {task.get('deadline')}\nОписание: {task.get('description') or '(отсутствует)'}\n\n",
                    reply_markup=get_edit_fields_keyboard(),
                    parse_mode='Markdown'
                )
                return states.EDIT_FIELD_SELECT
            else:
                await update.message.reply_text("❌ Ошибка при обновлении дедлайна.")
                return states.EDIT_FIELD_VALUE
        if action == 'date':
            # set chosen date and open time-picker (hours)
            context.user_data['deadline_date'] = date_val
            await update.message.reply_text("Выберите время дедлайна (час):", reply_markup=_build_hours_keyboard())
            return states.EDIT_FIELD_VALUE
    else:
        val = new_value

    # map priority emoji to storage value
    if field == 'priority':
        priority_map = {
            '🔴 Высокий': 'high',
            '🟡 Средний': 'medium',
            '🟢 Низкий': 'low'
        }
        mapped = priority_map.get(new_value, None)
        if mapped is not None:
            val = mapped
        else:
            # try to accept already-mapped values
            val = new_value

    success = update_note(task_id, user_id, {field: val})
    context.user_data.pop('field_to_edit', None)
    if success:
        task = db.get_task_by_id(task_id, user_id)
        await update.message.reply_text(
            f"✅ Поле обновлено. Текущие значения:\n*{task['task']}*\nПриоритет: {task.get('priority')}\nДедлайн: {task.get('deadline')}\nОписание: {task.get('description') or '(отсутствует)'}\n\n"
            "Выберите следующее поле для редактирования или 'Завершить редактирование'.",
            reply_markup=get_edit_fields_keyboard(),
            parse_mode='Markdown'
        )
        return states.EDIT_FIELD_SELECT
    else:
        await update.message.reply_text("❌ Ошибка при обновлении. Попробуйте снова или отмените.")
        return states.EDIT_FIELD_SELECT


async def show_completed_tasks(update: Update, context):
    user_id = update.effective_user.id
    tasks = db.get_tasks(user_id, done=True)
    if not tasks:
        await update.message.reply_text("✅ У вас нет выполненных задач для восстановления!", reply_markup=get_main_keyboard())
        return
    keyboard = get_completed_tasks_keyboard(tasks)
    await update.message.reply_text("♻️ Выберите задачу для восстановления:", reply_markup=keyboard)


async def handle_task_restore(update: Update, context):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    user_id = query.from_user.id
    success = db.restore_task(task_id, user_id)
    if success:
        await query.message.reply_text("✅ Задача успешно восстановлена!", reply_markup=get_main_keyboard())
    else:
        await query.message.reply_text("❌ Ошибка при восстановлении задачи", reply_markup=get_main_keyboard())
