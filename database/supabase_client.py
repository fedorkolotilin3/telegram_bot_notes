import uuid
from datetime import datetime
from supabase import create_client, Client
from config import Config
import logging

logger = logging.getLogger(__name__)

class SupabaseClient:
    def __init__(self):
        try:
            self.client: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing Supabase client: {e}")
            raise
    
    def add_task(self, user_id: int, task: str, priority: str = "medium", deadline: str = None) -> dict:
        """Добавление новой задачи"""
        try:
            task_data = {
                "user_id": user_id,
                "task": task,
                # supporting an optional detailed description
                "description": None,
                "priority": priority,
                "deadline": deadline,
                "is_done": False,
                "created_at": datetime.utcnow().isoformat()
            }
            
            response = self.client.table('tasks').insert(task_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error adding task: {e}")
            return None

    def update_task_description(self, task_id: int, user_id: int, description: str) -> bool:
        """Обновление подробного описания задачи"""
        try:
            response = self.client.table('tasks')\
                .update({'description': description})\
                .eq('id', task_id)\
                .eq('user_id', user_id)\
                .execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error updating task description: {e}")
            return False
    
    def update_task(self, task_id: int, user_id: int, fields: dict) -> bool:
        """Обновление произвольных полей задачи. fields - словарь колонка->значение"""
        if not fields:
            return False
        try:
            response = self.client.table('tasks')\
                .update(fields)\
                .eq('id', task_id)\
                .eq('user_id', user_id)\
                .execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error updating task fields: {e}")
            return False

    def get_task_by_name(self, user_id: int, name: str) -> dict:
        """Поиск задачи по части названия (case-insensitive) - возвращает первую подходящую"""
        try:
            response = self.client.table('tasks')\
                .select('*')\
                .eq('user_id', user_id)\
                .ilike('task', f"%{name}%")\
                .order('created_at', desc=True)\
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting task by name: {e}")
            return None
    
    def get_tasks(self, user_id: int, done: bool = False) -> list:
        """Получение задач пользователя"""
        try:
            response = self.client.table('tasks')\
                .select('*')\
                .eq('user_id', user_id)\
                .eq('is_done', done)\
                .order('created_at', desc=True)\
                .execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting tasks: {e}")
            return []
    
    def get_priority_tasks(self, user_id: int, priority: str = "high") -> list:
        """Получение задач по приоритету"""
        try:
            response = self.client.table('tasks')\
                .select('*')\
                .eq('user_id', user_id)\
                .eq('priority', priority)\
                .eq('is_done', False)\
                .order('created_at', desc=True)\
                .execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting priority tasks: {e}")
            return []
    
    def get_urgent_tasks(self, user_id: int) -> list:
        """Получение срочных задач (дедлайн сегодня или завтра)"""
        try:
            from datetime import datetime, timedelta
            today = datetime.now().date()
            tomorrow = today + timedelta(days=1)
            
            response = self.client.table('tasks')\
                .select('*')\
                .eq('user_id', user_id)\
                .eq('is_done', False)\
                .lte('deadline', tomorrow.isoformat())\
                .gte('deadline', today.isoformat())\
                .order('deadline')\
                .execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting urgent tasks: {e}")
            return []
    
    def mark_task_done(self, task_id: int, user_id: int) -> bool:
        """Отметка задачи как выполненной"""
        try:
            response = self.client.table('tasks')\
                .update({'is_done': True})\
                .eq('id', task_id)\
                .eq('user_id', user_id)\
                .execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error marking task as done: {e}")
            return False
    
    def delete_task(self, task_id: int, user_id: int) -> bool:
        """Удаление задачи"""
        try:
            response = self.client.table('tasks')\
                .delete()\
                .eq('id', task_id)\
                .eq('user_id', user_id)\
                .execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error deleting task: {e}")
            return False
    
    def get_task_by_id(self, task_id: int, user_id: int) -> dict:
        """Получение задачи по ID"""
        try:
            response = self.client.table('tasks')\
                .select('*')\
                .eq('id', task_id)\
                .eq('user_id', user_id)\
                .execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting task by ID: {e}")
            return None
        
    def get_all_tasks_with_users(self) -> list:
        """Получение всех задач всех пользователей (для уведомлений)"""
        try:
            response = self.client.table('tasks')\
                .select('*')\
                .eq('is_done', False)\
                .execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting all tasks: {e}")
            return []

# Создаем глобальный экземпляр клиента
db = SupabaseClient()