# supabase_client.py 

import os
import supabase
from dotenv import load_dotenv

load_dotenv()

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
database_url = os.getenv("DATABASE_URL") 

if not supabase_url or not supabase_key or not database_url:
    raise ValueError("SUPABASE_URL, SUPABASE_SERVICE_KEY, and DATABASE_URL must be set.")

supabase_client = supabase.create_client(supabase_url, supabase_key)