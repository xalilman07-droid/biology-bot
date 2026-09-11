import os
import logging
import asyncio
import sqlite3
import random
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import PollAnswer
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

# 1. BOT SOZLAMALARI
# Tokenni kod ichiga yozmaymiz, Render panelida xavfsiz muhitga joylaymiz
BOT_TOKEN = os.getenv("BOT_TOKEN")
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# 2. BAZANI SOZLASH (SQLite)
conn = sqlite3.connect("biology_bot.db")
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, ball INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS active_polls (poll_id TEXT PRIMARY KEY, user_id INTEGER)''')
conn.commit()

# 3. TESTLAR MA'LUMOTI
BIOLOGY_QUIZZES = [
    {"q": "O'simlik hujayrasining qobig'i nimadan iborat?", "o": ["Selyuloza", "Xitin", "Glikokaliks", "Murein"], "c": 0},
    {"q": "Fotosintez jarayoni hujayraning qaysi organoidida kechadi?", "o": ["Mitoxondriya", "Xloroplast", "Ribosoma", "Lizosoma"], "c": 1},
    {"q": "Odamda nechta qovurg'a bor?", "o": ["10 juft", "11 juft", "12 juft", "13 juft"], "c": 2},
    {"q": "DNK tarkibiga kirmaydigan azotli asosni toping.", "o": ["Adenin", "Timin", "Sitozin", "Urasil"], "c": 3},
    {"q": "Yurak necha kameradan iborat?", "o": ["2", "3", "4", "5"], "c": 2},
    {"q": "Gidra qaysi tipga kiradi?", "o": ["Bo'shliqichlilar", "Yassi qurtlar", "Bo'g'imoyoqlilar", "Molyuskalar"], "c": 0},
    {"q": "Qonning qizil hujayralari qanday nomlanadi?", "o": ["Leykotsitlar", "Trombotsitlar", "Eritrotsitlar", "Limfotsitlar"], "c": 2},
    {"q": "O'simliklarda suv transportini qaysi guruh to'qimalari bajaradi?", "o": ["Ksilema", "Floema", "Kambiy", "Epiderma"], "c": 0},
    {"q": "Insonda necha juft xromosoma bor?", "o": ["22 juft", "23 juft", "24 juft", "46 juft"], "c": 1},
    {"q": "Zamburug'lar hujayra devori nimadan iborat?", "o": ["Selyuloza", "Xitin", "Murein", "Pektin"], "c": 1}
]

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    name = message.from_user.full_name
    cursor.execute("INSERT OR REPLACE INTO users (user_id, name, ball) VALUES (?, ?, 0)", (user_id, name))
    conn.commit()
    await message.answer(f"Salom {name}! Biologiyadan testlar boshlandi!")
    
    selected_quizzes = random.sample(BIOLOGY_QUIZZES, k=min(10, len(BIOLOGY_QUIZZES)))
    for quiz in selected_quizzes:
        poll = await message.answer_poll(
            question=quiz["q"], options=quiz["o"], type="quiz", correct_option_id=quiz["c"], is_anonymous=False
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
        baho = "5 🏆" if ball >= 9 else ("4 🌟" if ball >= 7 else ("3 🔍" if ball >= 5 else "2 📚"))
        text = f"📊 **Kunlik natija:**\nIsm: {name}\nBall: {ball}/10\nBahongiz: {baho}"
        try: await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
        except: pass
    cursor.execute("DELETE FROM active_polls")
    cursor.execute("UPDATE users SET ball = 0")
    conn.commit()

# Render uxlab qolmasligi uchun kerakli HTTP qism
async def handle_http(request):
    return web.Response(text="Bot muvaffaqiyatli ishlayapti!")

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
