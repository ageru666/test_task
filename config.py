from dotenv import load_dotenv
import os
from aiogram import Bot
from aiogram.fsm.storage.memory import MemoryStorage

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
bot = Bot(token=TELEGRAM_TOKEN)
storage = MemoryStorage()