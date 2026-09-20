import os
import logging
import asyncio
import sqlite3
import json
import random
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

# 3. KATTA LOKAL SAVOLLAR BAZASI (AI ishlamay qolganda yoki zaxira uchun)
LARGE_BACKUP_QUIZZES = [
    {"q": "O'simlik hujayrasining qobig'i nimadan iborat?", "o": ["Selyuloza", "Xitin", "Glikokaliks", "Murein"], "c": 0},
    {"q": "Yurak necha kameradan iborat?", "o": ["2", "3", "4", "5"], "c": 2},
    {"q": "Fotosintez qaysi organoidda kechadi?", "o": ["Mitoxondriya", "Xloroplast", "Ribosoma", "Lizosoma"], "c": 1},
    {"q": "DNK tarkibiga kirmaydigan azotli asosni toping.", "o": ["Adenin", "Timin", "Sitozin", "Urasil"], "c": 3},
    {"q": "Insonda necha juft xromosoma bor?", "o": ["22 juft", "23 juft", "24 juft", "46 juft"], "c": 1},
    {"q": "Qaysi qon guruhi umumiy donor hisoblanadi?", "o": ["I (0)", "II (A)", "III (B)", "IV (AB)"], "c": 0},
    {"q": "Hujayraning 'energetik stansiyasi' qaysi organoid?", "o": ["Mitoxondriya", "Lizosoma", "Yadro", "Golji majmuasi"], "c": 0},
    {"q": "Odam organizmidagi eng uzun suyak qaysi?", "o": ["Son suyagi", "Yelka suyagi", "Lobiya suyagi", "Qovurg'a"], "c": 0},
    {"q": "Qonning qizil hujayralari nima deb ataladi?", "o": ["Eritrotsitlar", "Leykotsitlar", "Trombotsitlar", "Neironlar"], "c": 0},
    {"q": "O'simliklarda suv va mineral moddalarni o'tkazuvchi to'qima?", "o": ["Ksilema", "Floema", "Kambiy", "Epidermis"], "c": 0},
    {"q": "Bakteriyalar qaysi dunyoga kiradi?", "o": ["Prokariotlar", "Eukariotlar", "Zamburug'lar", "Viruslar"], "c": 0},
    {"q": "Odamda ovqat hazm qilish jarayoni qayerdan boshlanadi?", "o": ["Og'iz bo'shlig'idan", "Oshqozondan", "Qizilo'ngachdan", "O'nikki barmoqli ichakdan"], "c": 0},
    {"q": "Nuklein kislotalarni kim kashf etgan?", "o": ["Misher", "Uotson va Krik", "Mendel", "Darvin"], "c": 0},
    {"q": "Zamburug'lar hujayra devori nimadan tashkil topgan?", "o": ["Xitin", "Selyuloza", "Murein", "Lignin"], "c": 0},
    {"q": "Inson tana haroratini boshqaruvchi miya bo'limi?", "o": ["Gipotalamus", "Miyacha", "Uzunchoq miya", "Oraliq miya"], "c": 0},
    {"q": "Gipofiz bezi qaysi sistemaga kiradi?", "o": ["Endokrin", "Asab", "Qon aylanish", "Ayirish"], "c": 0},
    {"q": "O'simliklarda gaz almashinuvi qaysi a'zo orqali kechadi?", "o": ["Og'izchalar (Ustitsam)", "Tomirlar", "Ildiz tukchalari", "Po'stloq"], "c": 0},
    {"q": "Oqsil sintezi qaysi organoidda amalga oshiriladi?", "o": ["Ribosoma", "Mitoxondriya", "Lizosoma", "Peroksisoma"], "c": 0},
    {"q": "Genetika fanining asoschisi kim?", "o": ["Gregor Mendel", "Charlz Darvin", "Lamarck", "Toxir"], "c": 0},
    {"q": "Odam tanasidagi eng katta bez qaysi?", "o": ["Jigar", "Oshqozon osti bezi", "Qalqonsimon bez", "So'lak bezi"], "c": 0},
    {"q": "O'simliklarga yashil rang beruvchi pigment?", "o": ["Xlorofill", "Karotin", "Ksantofill", "Antotsian"], "c": 0},
    {"q": "Viruslar qanday tuzilishga ega?", "o": ["Hujayrasiz", "Bir hujayrali", "Kop hujayrali", "Yadroviy"], "c": 0},
    {"q": "Nerv sistemasining struktura va funksional birligi?", "o": ["Neiron", "Nefron", "Osteotsit", "Miot sit"], "c": 0},
    {"q": "Buyrakning funksional birligi nima deb ataladi?", "o": ["Nefron", "Neiron", "Alveola", "Lobula"], "c": 0},
    {"q": "O'pka pufakchalari nima deb ataladi?", "o": ["Alveola", "Bronxiola", "Nefron", "Villi"], "c": 0}
]

# 4. AI VA LOKAL BAZADAN SAVOL OLISH
def generate_biology_quizzes():
    topics = ["Zoologiya", "Botanika", "Anatomiya", "Genetika", "Sitologiya", "Ekologiya", "Evolyutsiya", "Biokimyo", "Mikrobiologiya"]
    selected_topic = random.choice(topics)
    seed = random.randint(10000, 99999)

    prompt = f"""
    Biologiyaning '{selected_topic}' sohasi bo'yicha 5 ta mutlaqo YANGI va turlicha test savollarini tayyorla.
    Oldingi berilgan savollar takrorlanmasin (Unique ID: {seed}).
    
    Javobni FAQAT quyidagi JSON formatida ber, ortiqcha matnsiz:
    [
      {{
        "q": "Savol matni",
        "o": ["Variant A", "Variant B", "Variant C", "Variant D"],
        "c": 0
      }}
    ]
    "c" - bu to'g'ri javob indeksi (0, 1, 2 yoki 3).
    """
    
    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash-exp", "gemini-1.5-flash"]
    
    for model_name in models_to_try:
        try:
            response = ai_client.models.generate_content(
                model=model_name,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "temperature": 1.0
                }
            )
            text = response.text.strip()
            data = json.loads(text)
            
            if isinstance(data, list) and len(data) >= 5:
                logging.info(f"AI orqali savollar yaratildi: {model_name} (Mavzu: {selected_topic})")
                return data[:5]
        except Exception as e:
            logging.warning(f"Model {model_name} xatolik berdi: {e}")
            continue

    logging.error("AI so'rovi muvaffaqiyatsiz bo'ldi. Lokal savollar bazasidan foydalanilmoqda.")
    
    # AI ishlamasa, katta bazadan tasodifiy 5 ta savol ajratib olinadi (hech qachon bir xil ketma-ketlik bo'lmaydi)
    return random.sample(LARGE_BACKUP_QUIZZES, 5)

# 5. BOT HANDLERLARI
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    name = message.from_user.full_name
    cursor.execute("INSERT OR REPLACE INTO users (user_id, name, ball) VALUES (?, ?, 0)", (user_id, name))
    conn.commit()
    
    msg = await message.answer(f"Salom {name}! Biologiyadan yangi savollar yuklanmoqda... 🧠")
    
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

# 6. KUNLIK NATIJALAR
async def daily_grading():
    cursor.execute("SELECT user_id, name, ball FROM users")
    users = cursor.fetchall()
    for user in users:
        user_id, name, ball = user
        baho = "5 🌟" if ball >= 4 else ("4 👍" if ball >= 3 else "3 😐")
        text = f"📊 **Kunlik natija:**\nIsm: {name}\nBall: {ball}\nBahongiz: {baho}"
        try:
            await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown")
        except Exception:
            pass
    cursor.execute("DELETE FROM active_polls")
    cursor.execute("UPDATE users SET ball = 0")
    conn.commit()

# 7. HTTP SERVER (Render uchun)
async def handle_http(request):
    return web.Response(text="Bot va AI muvaffaqiyatli ishlayapti!")

# 8. ASOSIY ISHGA TUSHIRISH
async def main():
    scheduler.add_job(daily_grading, 'cron', hour=20, minute=0)
    scheduler.start()
    
    await bot.delete_webhook(drop_pending_updates=True)
    
    app = web.Application()
    app.router.add_get('/', handle_http)
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
