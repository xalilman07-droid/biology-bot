import os
import logging
import asyncio
import sqlite3
import json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import PollAnswer
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web
from google import genai

# 1. BOT VA GEMINI SOZLAMALARI
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# 2. BAZANI SOZLASH (SQLite)
conn = sqlite3.connect("biology_bot.db")
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, ball INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS active_polls (poll_id TEXT PRIMARY KEY, user_id INTEGER)''')
conn.commit()

# 3. GEMINI AI ORQALI YANGI TESTLAR GENERATSIYA QILISH
def generate_biology_quizzes():
    prompt = """
    Biologiya fanidan 5 ta har xil va qiziqarli test savolini tayyorla.
    Javobni FAQAT to'g'ridan-to'g'ri JSON formatida ber, hech qanday qo'shimcha matn va markdown belgilarisiz!
    
    Format quyidagicha bo'lishi shart:
    [
      {
        "q": "Savol matni",
        "o": ["Variant A", "Variant B", "Variant C", "Variant D"],
        "c": 0
      }
    ]
    Eslatma: "c" - bu to'g'ri javobning indeksi (0, 1, 2 yoki 3).
    """
    try:
        response = ai_client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        text = response.text.strip()
        
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        
        data = json.loads(text.strip())
        if isinstance(data, list) and len(data) > 0:
            return data
        else:
            raise ValueError("Noto'g me'yoriy ma'lumot olindi")
    except Exception as e:
        logging.error(f"Gemini API xatoligi: {e}")
        # Zaxira savollar ro'yxati (Xatolik bo'lganda ishlaydi)
        return [
            {"q": "O'simlik hujayrasining qobig'i nimadan iborat?", "o": ["Selyuloza", "Xitin", "Glikokaliks", "Murein"], "c": 0},
            {"q": "Yurak necha kameradan iborat?", "o": ["2", "3", "4", "5"], "c": 2},
            {"q": "Fotosintez qaysi organoidda kechadi?", "o": ["Mitoxondriya", "Xloroplast", "Ribosoma", "Lizosoma"], "c": 1},
            {"q": "DNK tarkibiga kirmaydigan azotli asosni toping.", "o": ["Adenin", "Timin", "Sitozin", "Urasil"], "c": 3},
            {"q": "Insonda necha juft xromosoma bor?", "o": ["22 juft", "23 juft", "24 juft", "46 juft"], "c": 1}
        ]

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    name = message.from_user.full_name
    cursor.execute("INSERT OR REPLACE INTO users (user_id, name, ball) VALUES (?, ?, 0)", (user_id, name))
    conn.commit()
    
    msg = await message.answer(f"Salom {name}! AI biologiyadan yangi savollarni tayyorlamoqda, biroz kuting... 🧠")
    
    quizzes = generate_biology_quizzes()
    await msg.delete()
    
    await message.answer("Testlar boshlandi! Omad!")
    for quiz in quizzes:
        poll = await message.answer_poll(
            question=quiz["q"],
            options=quiz["o"],
            type="quiz",
            correct_option_id=quiz["c"],
            is_anonymous=False
        )
        cursor.execute("INSERT INTO active_polls (poll_id, user_id) VALUES (?, ?)", (poll.poll.id, user_id))
    conn.commit()

@dp.poll_answer()
async def handle_poll_answer(quiz_answer: PollAnswer):
    poll_id = quiz_answer.poll_id
    cursor.execute("SELECT user_id FROM active_polls WHERE poll_id = ?", (poll_id,))
    res = cursor.fetchone()
    if res:
        user_id = res[0]
        cursor.execute("UPDATE users SET ball = ball + 1 WHERE user_id = ?", (user_id,))
        conn.commit()

async def daily_grading():
    cursor.execute("SELECT user_id, name, ball FROM users")
    users = cursor.fetchall()
    for user in users:
        user_id, name, ball = user
        baho = "5 🌟" if ball >= 4 else ("4 👍" if ball >= 3 else "3 😐")
        text = f"📊 **Kunlik natija:**\nIsm: {name}\nBall: {ball}\nBahongiz: {baho}"
        try:
            await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
        except:
            pass
    cursor.execute("DELETE FROM active_polls")
    cursor.execute("UPDATE users SET ball = 0")
    conn.commit()

# Render veb-xizmati uchun HTTP server
async def handle_http(request):
    return web.Response(text="Bot va Gemini AI muvaffaqiyatli ishlayapti!")

async def main():
    scheduler.add_job(daily_grading, 'cron', hour=20, minute=0)
    scheduler.start()
    
    asyncio.create_task(dp.start_polling(bot))
    
    app = web.Application()
    app.router.add_get('/', handle_http)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
