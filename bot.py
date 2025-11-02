import logging
import signal
import sys
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from config import Config
from handlers.start import start_command, help_command
from handlers.actions import (
    show_my_tasks,
    show_important_tasks,
    show_urgent_tasks,
    show_tasks_for_completion,
    handle_task_completion,
    show_completed_tasks,
    handle_task_restore
)
from utils.keyboards import get_main_keyboard
from services.scheduler import NotificationScheduler, scheduler_instance
from handlers.tasks import get_general_edit_conversation, get_conversation_handler, get_description_conversation

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

class TaskManagerBot:
    def __init__(self):
        self.application = None
        self.scheduler = None
    
    def setup_handlers(self):
        """Настройка обработчиков команд"""
        # Регистрация обработчиков команд
        self.application.add_handler(CommandHandler("start", start_command))
        self.application.add_handler(CommandHandler("help", help_command))
        
        # Регистрация ConversationHandler для добавления задач
        self.application.add_handler(get_conversation_handler())
        # ConversationHandlers для просмотра/редактирования описаний задач
        self.application.add_handler(get_description_conversation())
        # general edit (replaces separate edit-description option)
        self.application.add_handler(get_general_edit_conversation())
        
        # Регистрация обработчиков сообщений (кнопки меню)
        self.application.add_handler(MessageHandler(filters.Regex('^(📋 Мои задачи)$'), show_my_tasks))
        self.application.add_handler(MessageHandler(filters.Regex('^(🔴 Важные задачи)$'), show_important_tasks))
        self.application.add_handler(MessageHandler(filters.Regex('^(⏰ Срочные задачи)$'), show_urgent_tasks))
        self.application.add_handler(MessageHandler(filters.Regex('^(✅ Завершить задачу)$'), show_tasks_for_completion))
        self.application.add_handler(MessageHandler(filters.Regex('^(♻️ Восстановить задачу)$'), show_completed_tasks))
        
        # Регистрация обработчиков inline кнопок
        self.application.add_handler(CallbackQueryHandler(handle_task_completion, pattern='^done_'))
        self.application.add_handler(CallbackQueryHandler(handle_task_restore, pattern='^restore_'))
        
        # Обработчик для неизвестных команд
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.unknown_command))
    
    async def unknown_command(self, update, context):
        """Обработчик неизвестных команд"""
        await update.message.reply_text(
            "Используйте кнопки меню для навигации :)",
            reply_markup=get_main_keyboard()
        )
    
    def setup_signal_handlers(self):
        """Настройка обработчиков сигналов для graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info("Received shutdown signal...")
            if self.scheduler:
                self.scheduler.stop_scheduler()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def run(self):
        """Запуск бота"""
        try:
            # Проверка конфигурации
            Config.validate()
            logger.info("Configuration validated successfully")
            
            # Создание приложения
            self.application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()
            logger.info("Telegram application created")
            
            # Настройка обработчиков
            self.setup_handlers()
            
            # Настройка планировщика уведомлений
            # Передаём токен, но не сам объект Application — это предотвращает
            # попытки создания weakref к экземпляру Application в сторонних
            # библиотеках (это вызывало ошибку на облачном хостинге).
            self.scheduler = NotificationScheduler(Config.TELEGRAM_BOT_TOKEN)
            self.scheduler.start_scheduler()
            
            # Настройка обработчиков сигналов
            self.setup_signal_handlers()
            
            # Запуск бота
            logger.info("Bot starting...")
            self.application.run_polling()
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            if self.scheduler:
                self.scheduler.stop_scheduler()
            sys.exit(1)

def main():
    """Основная функция запуска"""
    bot = TaskManagerBot()
    bot.run()

if __name__ == '__main__':
    main()