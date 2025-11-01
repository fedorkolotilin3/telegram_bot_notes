from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters
from database.supabase_client import db
from utils.keyboards import get_priority_keyboard, get_main_keyboard
from datetime import datetime

# Состояния для ConversationHandler
TASK, PRIORITY, DEADLINE = range(3)

async def start_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса добавления задачи"""
    await update.message.reply_text(
        "📝 Введите описание вашей задачи:",
        reply_markup=get_main_keyboard()
    )
    return TASK

async def receive_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение описания задачи"""
    context.user_data['task'] = update.message.text
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
    context.user_data['priority'] = priority_map.get(user_priority, 'medium')
    
    await update.message.reply_text(
        "📅 Введите срок выполнения в формате ГГГГ-ММ-ДД (например, 2024-12-31) "
        "или введите '-' чтобы пропустить:",
        reply_markup=get_main_keyboard()
    )
    return DEADLINE

async def receive_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение дедлайна и сохранение задачи"""
    user_input = update.message.text.strip()
    deadline = None
    
    if user_input != '-':
        try:
            # Проверяем корректность даты
            datetime.strptime(user_input, '%Y-%m-%d')
            deadline = user_input
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат даты! Используйте ГГГГ-ММ-ДД. Попробуйте снова:",
                reply_markup=get_main_keyboard()
            )
            return DEADLINE
    
    # Сохраняем задачу в базу данных
    user_id = update.effective_user.id
    task_data = db.add_task(
        user_id=user_id,
        task=context.user_data['task'],
        priority=context.user_data['priority'],
        deadline=deadline
    )
    
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
            PRIORITY: [MessageHandler(filters.Regex('^(🔴 Высокий|🟡 Средний|🟢 Низкий)$'), receive_priority)],
            DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_deadline)],
        },
        fallbacks=[MessageHandler(filters.Regex('^(Отмена|/cancel)$'), cancel_conversation)]
    )