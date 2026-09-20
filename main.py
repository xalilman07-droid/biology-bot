import os
import json
import logging
import random
from aiogram import Bot, Dispatcher, executor, types
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
dp = Dispatcher(bot)

# Google API uchun ishlaydigan eng yangi modellar ro'yxati
MODELS_TO_TRY = [
    "gemini-2.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro-latest"
]

def get_ai_question():
    """Gemini AI orqali biologik savol va javoblar yaratish"""
    if not GEMINI_API_KEY:
        return None

    prompt = (
        "Menga biologiya fanidan 1 ta o'rta yoki murakkab darajadagi test savolini tayyorlab ber. "
        "Javob faqat va faqat quyidagi JSON formatida bo'lsin, hech qanday ortiqcha matn ham, markdown ham bo'lmasin:\n"
        '{"q": "Savol matni", "o": ["Variant A", "Variant B", "Variant C", "Variant D"], "c": 0}\n'
        "Bu yerda 'c' - to'g'ri javobning indeksi (0, 1, 2 yoki 3)."
    )

    for model_name in MODELS_TO_TRY:
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            if response and response.text:
                clean_text = response.text.strip().replace("```json", "").replace("```", "")
                data = json.loads(clean_text)
                logging.info(f"AI savoli olindi, ishlatilgan model: {model_name}")
                return data
        except Exception as e:
            logging.warning(f"Model {model_name} xatolik berdi: {e}")
            continue

    logging.error("AI so'rovi muvaffaqiyatsiz bo'ldi. Lokal savollar bazasidan foydalanilmoqda.")
    return None

@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    await message.reply(
        "Xush kelibsiz! Men biologiya fanidan test topshirishingizga yordam beruvchi botman.\n\n"
        "Testni boshlash uchun /quiz buyrug'ini yuboring."
    )

@dp.message_handler(commands=['quiz'])
async def quiz_handler(message: types.Message):
    # Birinchi AI'dan savol olishga urinadi
    quiz_data = get_ai_question()
    
    # Agar AI javob bermasa, lokal bazadan oladi
    if not quiz_data:
        quiz_data = random.choice(BIOLOGY_QUESTIONS)

    await bot.send_poll(
        chat_id=message.chat.id,
        question=quiz_data["q"],
        options=quiz_data["o"],
        type='quiz',
        correct_option_id=quiz_data["c"],
        is_anonymous=False
    )

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
