"""Shared conversation state constants."""
# States for creation ConversationHandler
TASK, DESCRIPTION, PRIORITY, DEADLINE, TIME = range(5)

# States for description-related conversations
DESC_QUERY, EDIT_SELECT, EDIT_TEXT = range(3)

# States for general edit flow (start after prior states)
EDIT_TASK_SELECT, EDIT_FIELD_SELECT, EDIT_FIELD_VALUE = range(3, 6)

__all__ = [
    'TASK', 'DESCRIPTION', 'PRIORITY', 'DEADLINE', 'TIME',
    'DESC_QUERY', 'EDIT_SELECT', 'EDIT_TEXT',
    'EDIT_TASK_SELECT', 'EDIT_FIELD_SELECT', 'EDIT_FIELD_VALUE'
]
