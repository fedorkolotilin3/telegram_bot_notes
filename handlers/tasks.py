from telegram.ext import ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from utils.keyboards import (
    get_tasks_keyboard, get_main_keyboard, get_edit_fields_keyboard,
    get_priority_keyboard, get_completed_tasks_keyboard, get_skip_or_cancel_keyboard,
    get_cancel_keyboard, get_deadline_quick_keyboard
)
from utils.notes import update_note, create_note_from_user_data
from datetime import datetime

# import the moved async implementations and shared states
from handlers import actions
from handlers import states


# The async handler implementations live in handlers.actions



def get_description_conversation():
    from telegram.ext import CommandHandler, MessageHandler
    return ConversationHandler(
        entry_points=[
            CommandHandler('desc', actions.start_show_description_command),
            MessageHandler(filters.Regex('^(🔎 Описание)$'), actions.start_show_description_command)
        ],
        states={
            states.DESC_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, actions.wait_for_desc_query)]
        },
        fallbacks=[MessageHandler(filters.Regex('^(Отмена|/cancel)$'), lambda u, c: ConversationHandler.END)]
    )



def get_general_edit_conversation():
    from telegram.ext import CommandHandler, CallbackQueryHandler
    # handle_calendar_selection is defined in handlers.actions
    return ConversationHandler(
        entry_points=[
            CommandHandler('edittask', actions.start_general_edit),
            MessageHandler(filters.Regex('^(✏️ Редактировать задачу)$'), actions.start_general_edit)
        ],
        states={
            states.EDIT_TASK_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, actions.receive_task_for_general_edit)],
            states.EDIT_FIELD_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, actions.receive_field_choice)],
            states.EDIT_FIELD_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, actions.receive_new_field_value_general),
                CallbackQueryHandler(actions.handle_time_selection, pattern='^time_'),
                CallbackQueryHandler(actions.handle_calendar_selection)
            ]
        },
        fallbacks=[MessageHandler(filters.Regex('^(Отмена|/cancel)$'), lambda u, c: ConversationHandler.END)]
    )


def get_conversation_handler():
    """ConversationHandler for creating a new task (add task dialog)."""
    from telegram.ext import CommandHandler, CallbackQueryHandler

    return ConversationHandler(
        entry_points=[
            CommandHandler('addtask', actions.start_add_task),
            MessageHandler(filters.Regex('^(📝 Добавить задачу)$'), actions.start_add_task)
        ],
        states={
            states.TASK: [MessageHandler(filters.TEXT & ~filters.COMMAND, actions.receive_task)],
            states.DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, actions.receive_description)],
            states.PRIORITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, actions.receive_priority)],
            states.DEADLINE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, actions.receive_deadline),
                CallbackQueryHandler(actions.handle_calendar_selection)
            ],
            states.TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, actions.receive_time),
                CallbackQueryHandler(actions.handle_time_selection, pattern='^time_')
            ]
        },
        fallbacks=[MessageHandler(filters.Regex('^(Отмена|/cancel)$'), lambda u, c: ConversationHandler.END)]
    )