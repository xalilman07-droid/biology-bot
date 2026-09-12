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

# 1. LOGGING VA ASOSIY SOZLAMALAR
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Render-dan tokenni o'qiymiz
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Xatolik: BOT_TOKEN topilmadi!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# 2. MA'LUMOTLAR BAZASI (SQLite)
conn = sqlite3.connect("biology_bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, ball INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS active_polls (poll_id TEXT PRIMARY KEY, user_id INTEGER, quiz_index INTEGER)''')
conn.commit()

# 3. BIOLOGIYA TESTLARI (IZOHLARI BILAN)
BIOLOGY_QUIZZES = [
    {
        "q": "O'simlik hujayrasining qobig'i nimadan iborat?", 
        "o": ["Selyuloza", "Xitin", "Glikokaliks", "Murein"], 
        "c": 0,
        "e": "O'simlik hujayra devori asosan selyuloza (kletchatka)dan iborat. Xitin zamburug'larda, murein esa bakteriyalarda bo'ladi."
    },
    {
        "q": "Fotosintez jarayoni hujayraning qaysi organoidida kechadi?", 
        "o": ["Mitoxondriya", "Xloroplast", "Ribosoma", "Lizosoma"], 
        "c": 1,
        "e": "Fotosintez jarayoni o'simliklarning yashil qismi bo'lgan xloroplastlarda quyosh nuri ta'sirida amalga oshadi."
    },
    {
        "q": "Odamda nechta qovurg'a bor?", 
        "o": ["10 juft", "11 juft", "12 juft", "13 juft"], 
        "c": 2,
        "e": "Sog'lom odam skeletida 12 juft, ya'ni jami 24 ta qovurg'a to'sh suyagiga va umurtqalarga birikkan bo'ladi."
    },
    {
        "q": "DNK tarkibiga kirmaydigan azotli asosni toping.", 
        "o": ["Adenin", "Timin", "Sitozin", "Urasil"], 
        "c": 3,
        "e": "Urasil faqat RNK tarkibida bo'ladi. DNKda esa uning o'rnida Timin asosi qatnashadi."
    },
    {
        "q": "Yurak necha kameradan iborat?", 
        "o": ["2", "3", "4", "5"], 
        "c": 2,
        "e": "Sutemizuvchilar va odamda yurak 4 ta kameradan (2 ta bo'lmacha va 2 ta qorinchadan) iborat."
    },
    {
        "q": "Gidra qaysi tipga kiradi?", 
        "o": ["Bo'shliqichlilar", "Yassi qurtlar", "Bo'g'imoyoqlilar", "Molyuskalar"], 
        "c": 0,
        "e": "Chuchuk suv gidrasi ko'p hujayrali hayvonlarning Bo'shliqichlilar (Coelenterata) tipiga mansub."
    },
    {
        "q": "Qonning qizil hujayralari qanday nomlanadi?", 
        "o": ["Leykotsitlar", "Trombotsitlar", "Eritrotsitlar", "Limfotsitlar"], 
        "c": 2,
        "e": "Eritrotsitlar tarkibida gemoglobin bo'lganligi sababli qizil rangda bo'ladi va kislorod tashishga xizmat qiladi."
    },
    {
        "q": "O'simliklarda suv transportini qaysi guruh to'qimalari bajaradi?", 
        "o": ["Ksilema", "Floema", "Kambiy", "Epiderma"], 
        "c": 0,
        "e": "Ksilema (yog'ochlik naylari) suv va mineral moddalarni ildizdan tepaga o'tkazadi. Floema esa organik moddalarni tashiydi."
    },
    {
        "q": "Insonda necha juft xromosoma bor?", 
        "o": ["22 juft", "23 juft", "24 juft", "46 juft"], 
        "c": 1,
        "e": "Odam hujayrasida jami 46 ta xromosoma bor, bular o'zaro 23 juft bo'lib joylashadi (22 juft autosoma, 1 juft jinsiy xromosoma)."
    },
    {
        "q": "Zamburug'lar hujayra devori nimadan iborat?", 
        "o": ["Selyuloza", "Xitin", "Murein", "Pektin"], 
        "c": 1,
        "e": "Zamburug'lar hujayra qobig'i uglevod hisoblangan xitin moddasidan tashkil topgan bo'ladi."
    }
]

# 4. /START TUGMASI ISHLASHI
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    name = message.from_user.full_name
    
    # Bazada o'quvchini yangilash
    cursor.execute("INSERT OR REPLACE INTO users (user_id, name, ball) VALUES (?, ?, 0)", (user_id, name))
    conn.commit()
    
    await message.answer(
        f"Salom {name}! 👋\nBiologiya fanidan kunlik test imtihoniga xush kelibsiz.\n\n"
        f"Sizga hozir **10 ta tasodifiy test** yuboriladi. Har bir javob ortidan to'g'ri javob izohi chiqadi. Omad!"
    )
    
    # 10 ta tasodifiy testni olish
    shuffled_quizzes = list(enumerate(BIOLOGY_QUIZZES))
    selected = random.sample(shuffled_quizzes, k=min(10, len(BIOLOGY_QUIZZES)))
    
    # Ketma-ket yuborish
    for idx, quiz in selected:
        poll = await message.answer_poll(
            question=quiz["q"],
            options=quiz["o"],
            type="quiz",
            correct_option_id=quiz["c"],
            explanation=quiz["e"],       # O'QUVCHI UCHUN TO'G'RI JAVOB IZOHI
            is_anonymous=False           # KIM QAYSI VARIANTNI TANLAGANINI BILISH UCHUN!
        )
        cursor.execute("INSERT OR REPLACE INTO active_polls (poll_id, user_id, quiz_index) VALUES (?, ?, ?)", 
                       (poll.poll.id, user_id, idx))
    conn.commit()

# 5. O'QUVCHILAR QAYSI VARIANTNI TANLAGANINI LOGLASH VA BALL QO'SHISH
@dp.poll_answer()
async def handle_poll_answer(quiz_answer: PollAnswer):
    poll_id = quiz_answer.poll_id
    user_name = quiz_answer.user.full_name
    selected_option = quiz_answer.option_ids[0] if quiz_answer.option_ids else None
    
    cursor.execute("SELECT user_id, quiz_index FROM active_polls WHERE poll_id = ?", (poll_id,))
    res = cursor.fetchone()
    
    if res and selected_option is not None:
        user_id, quiz_index = res
        quiz_data = BIOLOGY_QUIZZES[quiz_index]
        
        chosen_text = quiz_data["o"][selected_option]
        correct_option = quiz_data["c"]
        
        # Terminal/Logda kim nima belgilaganini ko'rsatish
        logger.info(f"O'quvchi: {user_name} | Savol: {quiz_data['q']} | Tanladi: {chosen_text}")
        
        # To'g'ri topsa ball qo'shish
        if selected_option == correct_option:
            cursor.execute("UPDATE users SET ball = ball + 1 WHERE user_id = ?", (user_id,))
            conn.commit()

# 6. KUN YAKUNIDA 5 BALLIK TIZIMDA BAHOLASH (HAR KUNI SOAT 20:00 DA)
async def daily_grading():
    cursor.execute("SELECT user_id, name, ball FROM users")
    users = cursor.fetchall()
    
    for user in users:
        user_id, name, ball = user
        
        # 5 ballik baholash mezoni
        if ball >= 9:
            baho = "5 (A'lo) 🏆"
        elif ball >= 7:
            baho = "4 (Yaxshi) 🌟"
        elif ball >= 5:
            baho = "3 (Qoniqarli) 🔍"
        else:
            baho = "2 (Qoniqarsiz) 📚 Yana o'qishingiz kerak!"
            
        text = (f"📊 **Kunlik Imtihon Yakuni:**\n\n"
                f"👤 O'quvchi: {name}\n"
                f"✅ To'g'ri javoblar: {ball}/10 ta\n"
                f"🎯 Bugungi bahongiz: **{baho}**\n\n"
                f"Ertaga yangi testlarda ko'rishguncha!")
        try:
            await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Xabar yuborishda xato ({user_id}): {e}")
            
    # Ertangi kun uchun bazani tozalash
    cursor.execute("DELETE FROM active_polls")
    cursor.execute("UPDATE users SET ball = 0")
    conn.commit()

# 7. RENDER UXLAMASLIGI UCHUN VEB-SERVER (HTTP PORT)
async def handle_http(request):
    return web.Response(text="Biologiya Quiz Bot 24/7 Muammosiz Ishlamoqda!")

async def main():
    # Taymerni ishga tushirish (20:00 da baholaydi)
    scheduler.add_job(daily_grading, 'cron', hour=20, minute=0)
    scheduler.start()
    
    # Botni fonda ishga tushirish
    asyncio.create_task(dp.start_polling(bot))
    
    # Render talab qiladigan Web portni ochish
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
