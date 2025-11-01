from typing import Optional, Dict, Any
from datetime import datetime
from database.supabase_client import db
import logging

logger = logging.getLogger(__name__)


def _build_deadline_iso(date_part: Optional[str], time_part: Optional[str]) -> Optional[str]:
    """Собирает ISO строку дедлайна из даты и времени.
    date_part ожидается в формате YYYY-MM-DD или None.
    time_part ожидается в формате HH:MM или None.
    Возвращает None или ISO-представление (date or datetime).
    """
    if not date_part:
        return None

    # If time is provided, build datetime
    try:
        if time_part and time_part.strip() and time_part not in ('-', 'Пропустить'):
            # validate time
            datetime.strptime(time_part, '%H:%M')
            return f"{date_part}T{time_part}:00"
        # otherwise return date only
        # validate date
        datetime.strptime(date_part, '%Y-%m-%d')
        return date_part
    except Exception as e:
        logger.debug("Invalid date/time when building deadline: %s %s -> %s", date_part, time_part, e)
        return None


def create_note_from_user_data(user_id: int, user_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Создать задачу, собирая параметры из context.user_data.
    Ожидаемые ключи в user_data: 'task', 'priority', 'description', 'deadline_date', 'deadline_time'
    Возвращает добавленную запись или None.
    """
    task = user_data.get('task')
    if not task:
        logger.error('No task title provided')
        return None

    priority = user_data.get('priority', 'medium')
    description = user_data.get('description')
    date_part = user_data.get('deadline_date')
    time_part = user_data.get('deadline_time')

    deadline = _build_deadline_iso(date_part, time_part)

    return db.add_task(
        user_id=user_id,
        task=task,
        priority=priority,
        deadline=deadline,
        description=description
    )


def update_note(task_id: int, user_id: int, fields: Dict[str, Any]) -> bool:
    """Wrapper для обновления задачи. Преобразует deadline поля при необходимости.
    Если в fields есть 'deadline_date' или 'deadline_time', преобразует в единое поле 'deadline'.
    """
    # if composite parts provided, build deadline
    if 'deadline_date' in fields or 'deadline_time' in fields:
        date_part = fields.pop('deadline_date', None)
        time_part = fields.pop('deadline_time', None)
        deadline = _build_deadline_iso(date_part, time_part)
        fields['deadline'] = deadline

    # if explicit 'deadline' provided as '-' or empty, map to None
    if 'deadline' in fields and (fields['deadline'] in ('-', '', None) or str(fields['deadline']).lower() in ('none', 'null')):
        fields['deadline'] = None

    return db.update_task(task_id, user_id, fields)
