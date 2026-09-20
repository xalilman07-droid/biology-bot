import os
import json
import logging
import random
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from google import genai
from questions import BIOLOGY_QUESTIONS

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Yangi Gemini SDK klienti
ai_client = None
if GEMINI_API_KEY:
    ai_client = genai.Client(api_key=GEMINI_API_KEY)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_ai_question():
    """Gemini API orqali yangi savol oladi, agar xatolik bo'lsa lokal bazadan tanlaydi."""
    if ai_client:
        prompt = (
            "Biologiya fanidan ko'p variantli (A, B, C, D) 1 ta test savoli tuzing. "
            "Javobni FAQAT quyidagi JSON formatida qaytaring, ortiqcha matn yozmang:\n"
            "{\n"
            '  "question": "Savol matni",\n'
            '  "options": ["A variant", "B variant", "C variant", "D variant"],\n'
            '  "correct_option_id": 0\n'
            "}"
        )
        # 2026-yilda tavsiya etilgan rasmiy Gemini modellari
        models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash"]
        
        for model_name in models_to_try:
            try:
                response = ai_client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                # JSON matnini tozalash
                clean_json = response.text.strip().removeprefix("```json").removesuffix("```").strip()
                data = json.loads(clean_json)
                return data
            except Exception as e:
                logging.warning(f"Model {model_name} xatolik berdi: {e}")
                continue

    # Gemini ishlamay qolganda -> 300 talik questions.py bazasidan tasodifiy tanlash
    logging.info("Lokal savollar bazasidan foydalanilmoqda.")
    return random.choice(BIOLOGY_QUESTIONS)


@dp.message(Command("start"))
async def start_handler(message: Message):
    question_data = get_ai_question()
    
    # Viktorina (Quiz) yuborish
    await message.answer_poll(
        question=question_data["question"],
        options=question_data["options"],
        type="quiz",
        correct_option_id=question_data["correct_option_id"],
        is_anonymous=False
    )

async def main():
    logging.info("Bot ishga tushmoqda...")
    # TelegramConflictError va eski buyruqlarni tozalash
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
