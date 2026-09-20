import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from googletrans import Translator
import asyncio
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
translator = Translator()

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply("Xush kelibsiz! Biology Quiz Bot ishga tushdi.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)

