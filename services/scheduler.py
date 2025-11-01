import asyncio
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application
from database.supabase_client import db
from datetime import datetime, timedelta
import pytz

logger = logging.getLogger(__name__)

class NotificationScheduler:
    def __init__(self, application: Application):
        self.application = application
        self.scheduler = BackgroundScheduler()
        self.timezone = pytz.timezone('Europe/Moscow')
        
    def _run_async_job(self, time_of_day: str):
        """Обертка для запуска асинхронной функции в синхронном контексте"""
        try:
            # Создаем новую event loop для выполнения асинхронной функции
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Запускаем асинхронную функцию и ждем ее завершения
            loop.run_until_complete(self.send_daily_notification(time_of_day))
            loop.close()
            
        except Exception as e:
            logger.error(f"Error in async job wrapper: {e}")
    
    async def send_daily_notification(self, time_of_day: str):
        """Отправка ежедневных уведомлений"""
        try:
            # Получаем всех пользователей, у которых есть активные задачи
            all_tasks = db.get_all_tasks_with_users()
            
            # Группируем задачи по пользователям
            user_tasks = {}
            for task in all_tasks:
                if not task['is_done']:
                    user_id = task['user_id']
                    if user_id not in user_tasks:
                        user_tasks[user_id] = []
                    user_tasks[user_id].append(task)
            
            # Отправляем уведомления каждому пользователю
            for user_id, tasks in user_tasks.items():
                await self._send_user_notification(user_id, tasks, time_of_day)
                
        except Exception as e:
            logger.error(f"Error in daily notification: {e}")
    
    async def _send_user_notification(self, user_id: int, tasks: list, time_of_day: str):
        """Отправка уведомления конкретному пользователю"""
        try:
            # Получаем важные задачи (высокий приоритет)
            important_tasks = [task for task in tasks if task['priority'] == 'high' and not task['is_done']]
            
            # Получаем срочные задачи (дедлайн сегодня/завтра)
            urgent_tasks = self._get_urgent_tasks(tasks)
            
            # Формируем сообщение
            message = self._format_notification_message(time_of_day, important_tasks, urgent_tasks)
            
            # Отправляем сообщение
            await self.application.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Notification sent to user {user_id} at {time_of_day}")
            
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {e}")
    
    def _get_urgent_tasks(self, tasks: list) -> list:
        """Получение срочных задач (дедлайн сегодня или завтра)"""
        urgent_tasks = []
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        for task in tasks:
            if task['deadline']:
                try:
                    task_deadline = datetime.fromisoformat(task['deadline'].replace('Z', '+00:00')).date()
                    if task_deadline in [today, tomorrow]:
                        urgent_tasks.append(task)
                except ValueError:
                    continue
        
        return urgent_tasks
    
    def _format_notification_message(self, time_of_day: str, important_tasks: list, urgent_tasks: list) -> str:
        """Форматирование сообщения уведомления"""
        time_emojis = {
            'morning': '🌅',
            'afternoon': '☀️', 
            'evening': '🌙'
        }
        
        time_greetings = {
            'morning': 'Доброе утро!',
            'afternoon': 'Добрый день!',
            'evening': 'Добрый вечер!'
        }
        
        emoji = time_emojis.get(time_of_day, '⏰')
        greeting = time_greetings.get(time_of_day, 'Привет!')
        
        message = f"{emoji} *{greeting}*\n\n"
        
        # Добавляем важные задачи
        if important_tasks:
            message += "🔴 *Важные задачи:*\n"
            for task in important_tasks[:5]:  # Ограничиваем 5 задачами
                message += f"• {task['task']}\n"
            message += "\n"
        else:
            message += "✅ *Важных задач нет*\n\n"
        
        # Добавляем срочные задачи
        if urgent_tasks:
            message += "⏰ *Срочные задачи (дедлайн сегодня/завтра):*\n"
            for task in urgent_tasks[:5]:  # Ограничиваем 5 задачами
                deadline_str = ""
                if task['deadline']:
                    try:
                        deadline = datetime.fromisoformat(task['deadline'].replace('Z', '+00:00'))
                        deadline_str = f" ({deadline.strftime('%d.%m')})"
                    except:
                        deadline_str = ""
                message += f"• {task['task']}{deadline_str}\n"
        else:
            message += "✅ *Срочных задач нет*"
        
        # Добавляем общее количество задач
        total_tasks = len(important_tasks) + len(urgent_tasks)
        if total_tasks > 5:
            message += f"\n\n...и ещё {total_tasks - 5} задач"
        
        message += f"\n\n_Используйте /start для управления задачами_"
        
        return message
    
    def start_scheduler(self):
        """Запуск планировщика"""
        try:
            # Утреннее уведомление (8:00) - используем обертку для асинхронной функции
            self.scheduler.add_job(
                self._run_async_job,
                trigger=CronTrigger(hour=8, minute=0, timezone=self.timezone),
                args=['morning'],
                id='morning_notification'
            )
            
            # Дневное уведомление (13:00)
            self.scheduler.add_job(
                self._run_async_job,
                trigger=CronTrigger(hour=13, minute=0, timezone=self.timezone),
                args=['afternoon'],
                id='afternoon_notification'
            )
            
            # Вечернее уведомление (20:00)
            self.scheduler.add_job(
                self._run_async_job,
                trigger=CronTrigger(hour=22, minute=21, timezone=self.timezone),
                args=['evening'],
                id='evening_notification'
            )
            
            self.scheduler.start()
            logger.info("Notification scheduler started successfully")
            
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}")
    
    def stop_scheduler(self):
        """Остановка планировщика"""
        self.scheduler.shutdown()
        logger.info("Notification scheduler stopped")

# Глобальный экземпляр планировщика
scheduler_instance = None