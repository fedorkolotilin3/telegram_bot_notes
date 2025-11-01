from telegram import Update
from telegram.ext import ContextTypes
from utils.keyboards import get_main_keyboard

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    welcome_text = """
🤖 Добро пожаловать в Task Manager Bot!

Я помогу вам управлять вашими задачами и напоминаниями.

📋 Доступные команды:
• 📝 Добавить задачу - создать новую задачу
• 📋 Мои задачи - показать все активные задачи
• 🔴 Важные задачи - показать задачи с высоким приоритетом
• ⏰ Срочные задачи - показать задачи с ближайшим дедлайном
• ✅ Завершить задачу - отметить задачу как выполненную

Просто используйте кнопки меню для навигации!
    """
    await update.message.reply_text(
        welcome_text, 
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = """
📖 Справка по использованию бота:

*Добавление задачи:*
1. Нажмите "📝 Добавить задачу"
2. Введите описание задачи
3. Выберите приоритет
4. Укажите дедлайн (или пропустите)

*Просмотр задач:*
• "📋 Мои задачи" - все активные задачи
• "🔴 Важные задачи" - задачи с высоким приоритетом  
• "⏰ Срочные задачи" - задачи с ближайшим дедлайном

*Управление задачами:*
• "✅ Завершить задачу" - отметить задачу выполненной
    """
    await update.message.reply_text(
        help_text,
        reply_markup=get_main_keyboard(),
        parse_mode='Markdown'
    )