import os
import json
import logging
import random
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
import google.generativeai as genai
from questions import BIOLOGY_QUESTIONS

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Ishlaydigan model nomlari (birinchisi ishlamasa keyingisiga o'tadi)
MODELS_TO_TRY = [
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro-latest",
    "gemini-pro"
]

def get_ai_question():
    """Gemini API orqali yangi savol oladi, agar ishlamasa lokal bazadan qaytaradi."""
    if GEMINI_API_KEY:
        prompt = (
            "Biologiya fanidan ko'p variantli (A, B, C, D) 1 ta test savoli tuzing. "
            "Javobni quyidagi JSON formatida qaytaring:\n"
            "{\n"
            '  "question": "Savol matni",\n'
            '  "options": ["A variant", "B variant", "C variant", "D variant"],\n'
            '  "correct_option_id": 0\n'
            "}"
        )
        for model_name in MODELS_TO_TRY:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    prompt,
                    generation_config={"response_mime_type": "application/json"}
                )
                data = json.loads(response.text)
                return data
            except Exception as e:
                logging.warning(f"Model {model_name} xatolik berdi: {e}")
                continue

    # Gemini API ishlamasa yoki xato bersa -> 300 talik bazadan tasodifiy tanlash
    logging.info("Lokal savollar bazasidan foydalanilmoqda.")
    return random.choice(BIOLOGY_QUESTIONS)


@dp.message(Command("start"))
async def start_handler(message: Message):
    question_data = get_ai_question()
    
    # Poll (viktorina) ko'rinishida yuborish
    await message.answer_poll(
        question=question_data["question"],
        options=question_data["options"],
        type="quiz",
        correct_option_id=question_data["correct_option_id"],
        is_anonymous=False
    )

async def main():
    logging.info("Bot ishga tushmoqda...")
    # Polling boshlanishidan oldin eski webhook va to'planib qolgan xabarlarni tozalash (ConflictError oldini oladi)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
