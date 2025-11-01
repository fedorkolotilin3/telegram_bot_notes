import os
from supabase import create_client, Client
from dotenv import load_dotenv



load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")
print(url, key, sep = '\n')
supabase: Client = create_client(url, key)

# task_data = {
#     "user_id": 42501,
#     "task": task,
#     "priority": priority,
#     "deadline": deadline,
#     "is_done": False,
#     "created_at": datetime.utcnow().isoformat()
# }

# response = supabase.table('tasks').insert(task_data).execute()