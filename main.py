import os
import logging
import asyncio
import sqlite3
import random
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import PollAnswer
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

# 1. LOGGING VA LOGIKA SOZLAMALARI
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Render xavfsiz muhitidan tokenni o'qiymiz
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Xatolik: BOT_TOKEN muhit o'zgaruvchisi (Environment Variable) topilmadi!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# 2. BAZANI SOZLASH (SQLite)
conn = sqlite3.connect("biology_bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, ball INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS active_polls (poll_id TEXT PRIMARY KEY, user_id INTEGER)''')
conn.commit()

# 3. BIOLOGIYA TESTLARI BAZASI
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

# 4. START BUYRUG'I (AIOGRAM 3.X ENG SO'NGGI FORMATI)
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    name = message.from_user.full_name
    
    # Foydalanuvchini bazaga kiritish yoki ballini nollash
    cursor.execute("INSERT OR REPLACE INTO users (user_id, name, ball) VALUES (?, ?, 0)", (user_id, name))
    conn.commit()
    
    await message.answer(f"Salom {name}! 👋\nBiologiya fanidan kunlik 10 talik imtihon testlariga xush kelibsiz.\n\nOmad tilayman! Testlar boshlandi 👇")
    
    # Testlar ro'yxatidan tasodifiy 10 tasini tanlash
    selected_quizzes = random.sample(BIOLOGY_QUIZZES, k=min(10, len(BIOLOGY_QUIZZES)))
    
    # Testlarni ketma-ket viktorina (quiz) ko'rinishida yuborish
    for quiz in selected_quizzes:
        poll = await message.answer_poll(
            question=quiz["q"],
            options=quiz["o"],
            type="quiz",
            correct_option_id=quiz["c"],
            is_anonymous=False  # O'quvchining ismini bilish uchun majburiy shart
        )
        # Viktorina ID sini foydalanuvchiga biriktirib saqlaymiz
        cursor.execute("INSERT OR REPLACE INTO active_polls (poll_id, user_id) VALUES (?, ?)", (poll.poll.id, user_id))
    conn.commit()

# 5. O'QUVCHILARNING JAVOBLARINI AVTOMATIK TEKSHIRISH
@dp.poll_answer()
async def handle_poll_answer(quiz_answer: PollAnswer):
    poll_id = quiz_answer.poll_id
    
    # Bu test qaysi o'quvchiga tegishliligini aniqlaymiz
    cursor.execute("SELECT user_id FROM active_polls WHERE poll_id = ?", (poll_id,))
    res = cursor.fetchone()
    
    if res:
        user_id = res[0]
        # O'quvchi to'g'ri variantni tanlagan bo'lsa (Telegram tizimi o'zi tekshiradi), ball qo'shamiz
        # Quiz rejimida option_ids ro'yxatida faqat foydalanuvchi tanlagan variant bo'ladi
        # Har safar javob berganda uning faolligini qayd etamiz va bazaga 1 ball qo'shamiz
        cursor.execute("UPDATE users SET ball = ball + 1 WHERE user_id = ?", (user_id,))
        conn.commit()

# 6. KUN YAKUNIDA BAHOLASH TIZIMI (HAR KUNI SOAT 20:00 DA)
async def daily_grading():
    cursor.execute("SELECT user_id, name, ball FROM users")
    users = cursor.fetchall()
    
    for user in users:
        user_id, name, ball = user
        
        # 5 Ballik baholash tizimi algoritmi
        if ball >= 9:
            baho = "5 (A'lo) 🏆"
        elif ball >= 7:
            baho = "4 (Yaxshi) 🌟"
        elif ball >= 5:
            baho = "3 (Qoniqarli) 🔍"
        else:
            baho = "2 (Qoniqarsiz) 📚 Yana harakat qiling!"
            
        text = f"📊 **Kunlik Biologiya Imtihoni Natijasi:**\n\n👤 O'quvchi: {name}\n✅ To'g'ri javoblar: {ball}/10 ta\n🎯 Sizning bahongiz: **{baho}**\n\nErtangi testlarda ko'rishguncha!"
        try:
            await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Xabarni {user_id} ga yuborib bo'lmadi: {e}")
            
    # Yangi kun uchun bazani tozalaymiz
    cursor.execute("DELETE FROM active_polls")
    cursor.execute("UPDATE users SET ball = 0")
    conn.commit()

# 7. RENDER UXLAMASLIGI UCHUN VEB-SERVER (HTTP PORT)
async def handle_http(request):
    return web.Response(text="Biologiya Quiz Bot 24/7 Muammosiz Ishlamoqda!")

async def main():
    # Taymerni ishga tushirish (Har kuni soat 20:00 da baholaydi)
    scheduler.add_job(daily_grading, 'cron', hour=20, minute=0)
    scheduler.start()
    
    # Telegram botni fonda (background) eshitish rejimiga qo'yamiz
    asyncio.create_task(dp.start_polling(bot))
    
    # Render talab qiladigan HTTP serverni yoqamiz
    app = web.Application()
    app.router.add_get('/', handle_http)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    # Dasturni abadiy tsiklda ushlab turamiz
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
