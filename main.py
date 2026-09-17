import os
import json
import asyncio
import sqlite3
import logging
import aiohttp

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart
from aiogram.types import Message, PollAnswer
from aiogram.exceptions import TelegramRetryAfter, TelegramNetworkError
from aiohttp import web


# =========================
# SOZLAMALAR
# =========================

TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN:
    raise ValueError("BOT_TOKEN topilmadi!")

if not GEMINI_KEY:
    raise ValueError("GEMINI_API_KEY topilmadi!")

bot = Bot(TOKEN)
dp = Dispatcher()

logging.basicConfig(level=logging.INFO)


# =========================
# DATABASE
# =========================

db = sqlite3.connect(
    "biology.db",
    check_same_thread=False
)

db.execute("""
CREATE TABLE IF NOT EXISTS used (
    user_id INTEGER,
    question TEXT,
    UNIQUE(user_id, question)
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS polls (
    poll_id TEXT PRIMARY KEY,
    user_id INTEGER,
    answer INTEGER,
    explanation TEXT
)
""")

db.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    score INTEGER DEFAULT 0,
    total INTEGER DEFAULT 0
)
""")

db.commit()


# =========================
# GEMINI
# =========================

async def new_question(user_id):

    prompt = """
O'zbek tilida biologiyadan yangi test savoli yarat.

Talablar:
- 1 ta savol
- 4 ta javob
- faqat 1 ta to'g'ri javob
- ilmiy jihatdan to'g'ri
- o'rtacha yoki qiyin daraja
- takroriy savol yaratma

Faqat JSON qaytar:

{
 "question":"savol",
 "options":["A","B","C","D"],
 "answer":0,
 "explanation":"qisqa ilmiy izoh"
}
"""

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/gemini-3.8-flash:generateContent"
    )

    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.9,
            "responseMimeType": "application/json"
        }
    }

    headers = {
        "x-goog-api-key": GEMINI_KEY,
        "Content-Type": "application/json"
    }

    for _ in range(5):

        try:

            async with aiohttp.ClientSession() as s:

                async with s.post(
                    url,
                    json=data,
                    headers=headers,
                    timeout=40
                ) as r:

                    result = await r.json()

            text = result["candidates"][0]["content"]["parts"][0]["text"]

            q = json.loads(text)

            if len(q["options"]) != 4:
                continue

            if not 0 <= q["answer"] <= 3:
                continue

            old = db.execute(
                "SELECT 1 FROM used WHERE user_id=? AND question=?",
                (user_id, q["question"])
            ).fetchone()

            if old:
                continue

            db.execute(
                "INSERT OR IGNORE INTO used VALUES (?,?)",
                (user_id, q["question"])
            )

            db.commit()

            return q

        except Exception as e:
            logging.error(e)
            await asyncio.sleep(2)

    return None


# =========================
# QUIZ YUBORISH
# =========================

async def send_quiz(user_id):

    q = await new_question(user_id)

    if not q:
        await bot.send_message(
            user_id,
            "⏳ Yangi savol yaratishda muammo bo'ldi. "
            "Yana urinib ko'raman."
        )
        return

    for attempt in range(5):

        try:

            poll = await bot.send_poll(
                user_id,
                q["question"],
                q["options"],
                type="quiz",
                correct_option_ids=[q["answer"]],
                explanation=q["explanation"],
                is_anonymous=False,
                allows_multiple_answers=False
            )

            db.execute(
                """
                INSERT OR REPLACE INTO polls
                VALUES (?,?,?,?)
                """,
                (
                    poll.id,
                    user_id,
                    q["answer"],
                    q["explanation"]
                )
            )

            db.commit()

            return

        except TelegramRetryAfter as e:

            await asyncio.sleep(
                e.retry_after + 1
            )

        except TelegramNetworkError:

            await asyncio.sleep(
                2 ** attempt
            )

        except Exception as e:

            logging.error(e)
            await asyncio.sleep(2)


# =========================
# START
# =========================

@dp.message(CommandStart())
async def start(message: Message):

    uid = message.from_user.id

    db.execute(
        "INSERT OR IGNORE INTO users(user_id) VALUES(?)",
        (uid,)
    )

    db.commit()

    await message.answer(
        "🧬 Biologiya Quiz\n\n"
        "Yangi savol tayyorlanmoqda..."
    )

    await send_quiz(uid)


# =========================
# JAVOB
# =========================

@dp.poll_answer()
async def answer(data: PollAnswer):

    row = db.execute(
        """
        SELECT user_id,answer,explanation
        FROM polls
        WHERE poll_id=?
        """,
        (data.poll_id,)
    ).fetchone()

    if not row:
        return

    uid, correct, explanation = row

    if data.user.id != uid:
        return

    selected = data.option_ids[0]

    ok = selected == correct

    db.execute(
        """
        UPDATE users
        SET score=score+?,
            total=total+1
        WHERE user_id=?
        """,
        (int(ok), uid)
    )

    db.execute(
        "DELETE FROM polls WHERE poll_id=?",
        (data.poll_id,)
    )

    db.commit()

    score, total = db.execute(
        "SELECT score,total FROM users WHERE user_id=?",
        (uid,)
    ).fetchone()

    text = (
        "✅ To'g'ri!\n\n"
        if ok else
        "❌ Noto'g'ri!\n\n"
    )

    text += (
        f"💡 {explanation}\n\n"
        f"🏆 Ball: {score}\n"
        f"📊 Natija: {score}/{total}\n\n"
        "🔄 Yangi savol..."
    )

    await bot.send_message(uid, text)

    await asyncio.sleep(2)

    await send_quiz(uid)


# =========================
# RENDER WEB SERVER
# =========================

async def home(request):
    return web.Response(
        text="Biology Quiz Bot ishlayapti ✅"
    )


async def main():

    app = web.Application()
    app.router.add_get("/", home)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", 8080))

    await web.TCPSite(
        runner,
        "0.0.0.0",
        port
    ).start()

    while True:

        try:

            await dp.start_polling(
                bot,
                allowed_updates=[
                    "message",
                    "poll_answer"
                ]
            )

        except Exception as e:

            logging.error(
                "Bot xatosi: %s",
                e
            )

            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
