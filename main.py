import os
import asyncio
import logging
import sqlite3
import random
import hashlib
import time

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, PollAnswer

from google import genai
from questions import BIOLOGY_QUESTIONS


# =========================
# SOZLAMALAR
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TEST_SIZE = 20
DB_FILE = "questions.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

gemini = None
if GEMINI_API_KEY:
    gemini = genai.Client(api_key=GEMINI_API_KEY)


# =========================
# DATABASE
# =========================

def db():
    con = sqlite3.connect(DB_FILE)
    con.execute("""
        CREATE TABLE IF NOT EXISTS used_questions (
            user_id INTEGER,
            question_hash TEXT,
            question TEXT,
            PRIMARY KEY(user_id, question_hash)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            user_id INTEGER PRIMARY KEY,
            questions TEXT,
            current INTEGER,
            score INTEGER
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS polls (
            poll_id TEXT PRIMARY KEY,
            user_id INTEGER
        )
    """)
    con.commit()
    return con


def qhash(text):
    return hashlib.sha256(
        text.strip().lower().encode("utf-8")
    ).hexdigest()


def get_used(user_id):
    con = db()
    rows = con.execute(
        "SELECT question FROM used_questions WHERE user_id=?",
        (user_id,)
    ).fetchall()
    con.close()
    return {x[0] for x in rows}


def save_used(user_id, question):
    con = db()
    con.execute(
        "INSERT OR IGNORE INTO used_questions VALUES (?, ?, ?)",
        (user_id, qhash(question), question)
    )
    con.commit()
    con.close()


def save_session(user_id, questions, current=0, score=0):
    con = db()
    con.execute(
        "INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?)",
        (user_id, str(questions), current, score)
    )
    con.commit()
    con.close()


def delete_session(user_id):
    con = db()
    con.execute(
        "DELETE FROM sessions WHERE user_id=?",
        (user_id,)
    )
    con.commit()
    con.close()


# =========================
# LOCAL SAVOLLAR
# =========================

def local_questions(user_id):
    used = get_used(user_id)

    available = [
        q for q in BIOLOGY_QUESTIONS
        if q.get("q") not in used
    ]

    random.shuffle(available)

    result = []

    for q in available:
        if len(result) >= TEST_SIZE:
            break

        result.append({
            "question": q["q"],
            "options": q["o"],
            "correct_option_id": q["c"],
            "explanation": "Bu savol mahalliy biologiya savollar bazasidan olindi."
        })

    return result


# =========================
# GEMINI
# =========================

def gemini_questions(user_id, count):
    if not gemini:
        return []

    used = list(get_used(user_id))[-100:]

    prompt = f"""
Biologiya fanidan {count} ta yangi test savoli yarat.

Talablar:
- Har bir savolda 4 ta variant bo'lsin.
- Faqat bitta to'g'ri javob bo'lsin.
- Savollar bir-biridan farqli bo'lsin.
- Oldin ishlatilgan savollarni takrorlama.
- Savollar o'zbek tilida bo'lsin.
- Savol ilmiy jihatdan to'g'ri bo'lsin.
- Har bir savol uchun qisqa izoh yoz.

Javobni FAQAT JSON array ko'rinishida ber:

[
  {{
    "question": "...",
    "options": ["...", "...", "...", "..."],
    "correct_option_id": 0,
    "explanation": "..."
  }}
]

Oldin ishlatilgan savollar:
{used}
"""

    for attempt in range(2):
        try:
            response = gemini.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )

            text = response.text.strip()

            if text.startswith("```"):
                text = text.replace("```json", "")
                text = text.replace("```", "")
                text = text.strip()

            import json
            data = json.loads(text)

            result = []

            for q in data:
                if (
                    isinstance(q.get("question"), str)
                    and len(q.get("options", [])) == 4
                    and isinstance(q.get("correct_option_id"), int)
                    and 0 <= q["correct_option_id"] <= 3
                ):
                    result.append(q)

            return result[:count]

        except Exception as e:
            logging.error("Gemini xatosi: %s", e)
            time.sleep(2)

    return []


# =========================
# TEST YARATISH
# =========================

def make_test(user_id):
    result = []

    # Avval Gemini
    result.extend(
        gemini_questions(user_id, TEST_SIZE)
    )

    # Yetishmasa local baza
    if len(result) < TEST_SIZE:
        local = local_questions(user_id)

        existing = {
            q["question"].strip().lower()
            for q in result
        }

        for q in local:
            if q["question"].strip().lower() not in existing:
                result.append(q)
                existing.add(q["question"].strip().lower())

            if len(result) >= TEST_SIZE:
                break

    # Variantlarni aralashtirish
    for q in result:
        correct = q["options"][q["correct_option_id"]]

        random.shuffle(q["options"])

        q["correct_option_id"] = q["options"].index(correct)

    return result[:TEST_SIZE]


# =========================
# SAVOL YUBORISH
# =========================

async def send_question(user_id):
    con = db()
    row = con.execute(
        "SELECT questions, current, score FROM sessions WHERE user_id=?",
        (user_id,)
    ).fetchone()
    con.close()

    if not row:
        return

    import ast

    questions = ast.literal_eval(row[0])
    current = row[1]
    score = row[2]

    if current >= len(questions):
        await finish_test(user_id, score, len(questions))
        return

    q = questions[current]

    for attempt in range(3):
        try:
            poll = await bot.send_poll(
                chat_id=user_id,
                question=f"{current + 1}/{len(questions)}. {q['question']}",
                options=q["options"],
                type="quiz",
                correct_option_id=q["correct_option_id"],
                is_anonymous=False
            )

            con = db()
            con.execute(
                "INSERT OR REPLACE INTO polls VALUES (?, ?)",
                (poll.poll.id, user_id)
            )
            con.commit()
            con.close()

            save_used(user_id, q["question"])
            return

        except Exception as e:
            logging.error(
                "Savol yuborishda xato (%s/3): %s",
                attempt + 1,
                e
            )
            await asyncio.sleep(2)

    await bot.send_message(
        user_id,
        "⚠️ Savolni yuborishda vaqtinchalik xatolik yuz berdi. "
        "Iltimos, birozdan keyin /start bosing."
    )


# =========================
# START
# =========================

@dp.message(Command("start"))
async def start(message: Message):
    user_id = message.from_user.id

    await message.answer(
        "🧬 Biologiya testi tayyorlanmoqda...\n"
        "20 ta savol tayyorlayapman."
    )

    questions = await asyncio.to_thread(
        make_test,
        user_id
    )

    if not questions:
        await message.answer(
            "❌ Hozircha savollar tayyor bo'lmadi. "
            "Keyinroq yana /start bosing."
        )
        return

    save_session(user_id, questions, 0, 0)

    await send_question(user_id)


# =========================
# POLL JAVOBI
# =========================

@dp.poll_answer()
async def poll_answer(answer: PollAnswer):
    poll_id = answer.poll_id

    con = db()
    row = con.execute(
        "SELECT user_id FROM polls WHERE poll_id=?",
        (poll_id,)
    ).fetchone()
    con.close()

    if not row:
        return

    user_id = row[0]

    con = db()
    row = con.execute(
        "SELECT questions, current, score FROM sessions WHERE user_id=?",
        (user_id,)
    ).fetchone()
    con.close()

    if not row:
        return

    import ast

    questions = ast.literal_eval(row[0])
    current = row[1]
    score = row[2]

    q = questions[current]

    if answer.option_ids:
        if answer.option_ids[0] == q["correct_option_id"]:
            score += 1
            await bot.send_message(
                user_id,
                "✅ To'g'ri!\n\n"
                f"💡 Izoh: {q.get('explanation', '')}"
            )
        else:
            correct = q["options"][q["correct_option_id"]]

            await bot.send_message(
                user_id,
                f"❌ Noto'g'ri.\n"
                f"✅ To'g'ri javob: {correct}\n\n"
                f"💡 Izoh: {q.get('explanation', '')}"
            )

    current += 1

    con = db()
    con.execute(
        "UPDATE sessions SET current=?, score=? WHERE user_id=?",
        (current, score, user_id)
    )
    con.commit()
    con.close()

    con = db()
    con.execute(
        "DELETE FROM polls WHERE poll_id=?",
        (poll_id,)
    )
    con.commit()
    con.close()

    await asyncio.sleep(0.5)

    if current >= len(questions):
        await finish_test(user_id, score, len(questions))
    else:
        await send_question(user_id)


# =========================
# YAKUN
# =========================

async def finish_test(user_id, score, total):
    percent = round(score / total * 100)

    await bot.send_message(
        user_id,
        "🎉 Test yakunlandi!\n\n"
        f"📊 Natija: {score}/{total}\n"
        f"📈 Foiz: {percent}%\n\n"
        "🔄 Yangi test uchun /start bosing."
    )

    delete_session(user_id)


# =========================
# RENDER HEALTH SERVER
# =========================

async def health(request):
    return web.Response(
        text="Biology Bot is running ✅"
    )


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", "10000"))

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    logging.info(
        "Health server: http://0.0.0.0:%s",
        port
    )


# =========================
# MAIN
# =========================

async def main():
    db()

    await start_web_server()

    logging.info("🚀 Biology bot ishga tushdi!")

    while True:
        try:
            await bot.delete_webhook(
                drop_pending_updates=False
            )

            await dp.start_polling(
                bot,
                handle_signals=False
            )

        except Exception as e:
            logging.error(
                "Polling xatosi: %s",
                e
            )

            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
