import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "98mUStcarE$")
DB_NAME = os.getenv("DB_NAME", "expenses_db")
DB_HOST = os.getenv("DB_HOST", "localhost")