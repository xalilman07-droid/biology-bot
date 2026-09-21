import os
import json
import random
import sqlite3
import logging
import asyncio
import hashlib

from difflib import SequenceMatcher
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, PollAnswer
from google import genai

from questions import BIOLOGY_QUESTIONS


# ==============================
# SOZLAMALAR
# ==============================

TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

DB = "biology.db"
TEST_SIZE = 20

if not TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# ==============================
# BOT
# ==============================

bot = Bot(TOKEN)
dp = Dispatcher()

ai = genai.Client(
    api_key=GEMINI_KEY
) if GEMINI_KEY else None


# ==============================
# DATABASE
# ==============================

def connect():
    c = sqlite3.connect(
        DB,
        timeout=30
    )
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db():

    c = connect()

    c.execute("""
    CREATE TABLE IF NOT EXISTS used (
        user_id INTEGER,
        qhash TEXT,
        question TEXT,
        PRIMARY KEY(user_id, qhash)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        user_id INTEGER PRIMARY KEY,
        data TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS polls (
        poll_id TEXT PRIMARY KEY,
        user_id INTEGER,
        question_index INTEGER,
        correct INTEGER,
        explanation TEXT
    )
    """)

    c.commit()
    c.close()


def qhash(q):
    return hashlib.sha256(
        " ".join(
            q.lower().split()
        ).encode()
    ).hexdigest()


def used(user_id, q):

    c = connect()

    r = c.execute(
        """
        SELECT 1 FROM used
        WHERE user_id=? AND qhash=?
        """,
        (user_id, qhash(q))
    ).fetchone()

    c.close()

    return r is not None


def save_used(user_id, q):

    c = connect()

    c.execute(
        """
        INSERT OR IGNORE INTO used
        VALUES (?, ?, ?)
        """,
        (
            user_id,
            qhash(q),
            q
        )
    )

    c.commit()
    c.close()


def old_questions(user_id):

    c = connect()

    rows = c.execute(
        """
        SELECT question FROM used
        WHERE user_id=?
        """,
        (user_id,)
    ).fetchall()

    c.close()

    return [x[0] for x in rows]


# ==============================
# SESSION
# ==============================

def save_session(user_id, data):

    c = connect()

    c.execute(
        """
        INSERT OR REPLACE INTO sessions
        VALUES (?, ?)
        """,
        (
            user_id,
            json.dumps(
                data,
                ensure_ascii=False
            )
        )
    )

    c.commit()
    c.close()


def load_session(user_id):

    c = connect()

    r = c.execute(
        """
        SELECT data FROM sessions
        WHERE user_id=?
        """,
        (user_id,)
    ).fetchone()

    c.close()

    if not r:
        return None

    try:
        return json.loads(r[0])
    except:
        return None


# ==============================
# SAVOL TEKSHIRISH
# ==============================

def similar(a, b, limit=0.82):

    return SequenceMatcher(
        None,
        a.lower(),
        b.lower()
    ).ratio() >= limit


def valid(x):

    if not isinstance(x, dict):
        return None

    q = str(
        x.get("question", "")
    ).strip()

    options = x.get("options")
    correct = x.get(
        "correct_option_id"
    )

    if (
        not q
        or not isinstance(options, list)
        or len(options) != 4
        or correct not in range(4)
    ):
        return None

    options = [
        str(x).strip()
        for x in options
    ]

    if len(set(options)) != 4:
        return None

    return {
        "question": q,
        "options": options,
        "correct_option_id": correct,
        "explanation": str(
            x.get(
                "explanation",
                "Biologik izoh mavjud emas."
            )
        )
    }


def shuffle_question(q):

    q = dict(q)

    correct = q[
        "options"
    ][
        q["correct_option_id"]
    ]

    random.shuffle(
        q["options"]
    )

    q[
        "correct_option_id"
    ] = q["options"].index(
        correct
    )

    return q


# ==============================
# GEMINI
# ==============================

def gemini_questions(
    user_id,
    amount,
    current
):

    if not ai:
        return []

    old = old_questions(
        user_id
    ) + current

    prompt = f"""
Biologiyadan {amount} ta murakkab
test savoli yarat.

Mavzularni aralashtir:
genetika, hujayra, molekulyar biologiya,
biokimyo, anatomiya, fiziologiya,
botanika, mikrobiologiya, ekologiya,
evolyutsiya.

Har birida:
- 4 variant
- faqat 1 to'g'ri javob
- ilmiy izoh

Bu savollarni takrorlama:

{chr(10).join(old[-100:])}

Faqat JSON ARRAY:

[
{{
"question":"...",
"options":["...","...","...","..."],
"correct_option_id":0,
"explanation":"..."
}}
]
"""

    for attempt in range(3):

        try:

            r = ai.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )

            text = r.text.strip()

            a = text.find("[")
            b = text.rfind("]")

            if a < 0 or b < 0:
                continue

            data = json.loads(
                text[a:b + 1]
            )

            result = []

            for x in data:

                x = valid(x)

                if not x:
                    continue

                q = x["question"]

                if used(user_id, q):
                    continue

                if any(
                    similar(q, z)
                    for z in old + [
                        y["question"]
                        for y in result
                    ]
                ):
                    continue

                result.append(x)

                if len(result) == amount:
                    break

            return result

        except Exception as e:

            logging.warning(
                "Gemini xatosi: %s",
                e
            )

            time = 2 ** attempt
            asyncio.run(
                asyncio.sleep(time)
            )

    return []


# ==============================
# LOCAL SAVOLLAR
# ==============================

def local_questions(
    user_id,
    amount,
    current
):

    old = old_questions(
        user_id
    ) + current

    questions = list(
        BIOLOGY_QUESTIONS
    )

    random.shuffle(
        questions
    )

    result = []

    for x in questions:

        q = x.get("q")
        options = x.get("o")
        correct = x.get("c")

        if (
            not q
            or not isinstance(options, list)
            or len(options) != 4
            or correct not in range(4)
        ):
            continue

        if used(user_id, q):
            continue

        if any(
            similar(q, z)
            for z in old
        ):
            continue

        result.append({
            "question": q,
            "options": list(options),
            "correct_option_id": correct,
            "explanation": x.get(
                "e",
                "Bu savol biologiya bazasidan olindi."
            )
        })

        old.append(q)

        if len(result) >= amount:
            break

    return result


# ==============================
# TEST YARATISH
# ==============================

async def make_test(user_id):

    result = []

    # Gemini
    if ai:

        for _ in range(4):

            need = min(
                5,
                TEST_SIZE - len(result)
            )

            if need <= 0:
                break

            batch = await asyncio.to_thread(
                gemini_questions,
                user_id,
                need,
                [
                    x["question"]
                    for x in result
                ]
            )

            for q in batch:
                result.append(
                    shuffle_question(q)
                )

    # Local baza
    if len(result) < TEST_SIZE:

        need = (
            TEST_SIZE
            - len(result)
        )

        local = await asyncio.to_thread(
            local_questions,
            user_id,
            need,
            [
                x["question"]
                for x in result
            ]
        )

        for q in local:
            result.append(
                shuffle_question(q)
            )

    if len(result) < TEST_SIZE:
        return None

    random.shuffle(result)

    return result


# ==============================
# POLL YUBORISH
# ==============================

async def send_question(user_id):

    session = load_session(
        user_id
    )

    if not session:
        return

    index = session["current"]

    if index >= TEST_SIZE:

        await finish(user_id)
        return

    q = session[
        "questions"
    ][index]

    for attempt in range(3):

        try:

            poll = await bot.send_poll(

                user_id,

                (
                    f"🧬 SAVOL "
                    f"{index + 1}/{TEST_SIZE}\n\n"
                    + q["question"]
                ),

                q["options"],

                type="quiz",

                correct_option_id=
                q["correct_option_id"],

                is_anonymous=False
            )

            if not poll.poll:
                raise Exception(
                    "Poll yaratilmadi"
                )

            c = connect()

            c.execute(
                """
                INSERT OR REPLACE INTO polls
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    poll.poll.id,
                    user_id,
                    index,
                    q["correct_option_id"],
                    q["explanation"]
                )
            )

            c.commit()
            c.close()

            # Faqat muvaffaqiyatli yuborilgandan keyin
            # savol ishlatilgan deb belgilanadi.
            save_used(
                user_id,
                q["question"]
            )

            return

        except Exception as e:

            logging.warning(
                "Poll xatosi %s/3: %s",
                attempt + 1,
                e
            )

            await asyncio.sleep(
                2 ** attempt
            )


# ==============================
# START
# ==============================

@dp.message(
    Command("start")
)
async def start(
    message: Message
):

    user_id = message.from_user.id

    await message.answer(
        "🧬 BIOLOGIYA QUIZ\n\n"
        "⏳ 20 ta yangi savol "
        "tayyorlanmoqda..."
    )

    try:

        questions = await make_test(
            user_id
        )

        if not questions:

            await message.answer(
                "❌ Hozircha 20 ta yangi "
                "savol tayyorlab bo'lmadi."
            )
            return

        session = {
            "questions": questions,
            "current": 0,
            "score": 0,
            "finished": False
        }

        save_session(
            user_id,
            session
        )

        await message.answer(
            "✅ TEST TAYYOR!\n\n"
            "🚀 Boshladik!\n"
            "Javob berganingizdan keyin "
            "keyingi savol avtomatik chiqadi."
        )

        await send_question(
            user_id
        )

    except Exception as e:

        logging.exception(
            "START xatosi: %s",
            e
        )

        await message.answer(
            "⚠️ Vaqtinchalik xatolik.\n"
            "Birozdan keyin /start bosing."
        )


# ==============================
# POLL JAVOBI
# ==============================

@dp.poll_answer()
async def answer(
    poll: PollAnswer
):

    c = connect()

    row = c.execute(
        """
        SELECT
            user_id,
            question_index,
            correct,
            explanation
        FROM polls
        WHERE poll_id=?
        """,
        (poll.poll_id,)
    ).fetchone()

    c.close()

    if not row:
        return

    user_id, index, correct, explanation = row

    if poll.user.id != user_id:
        return

    session = load_session(
        user_id
    )

    if not session:
        return

    if session["current"] != index:
        return

    selected = (
        poll.option_ids[0]
        if poll.option_ids
        else -1
    )

    if selected == correct:

        session["score"] += 1

        text = "✅ TO'G'RI JAVOB!"

    else:

        text = "❌ NOTO'G'RI JAVOB!"

    text += (
        f"\n\n📊 Natija: "
        f"{session['score']}/{index + 1}"
    )

    if explanation:
        text += (
            "\n\n💡 IZOH:\n"
            + explanation
        )

    await bot.send_message(
        user_id,
        text
    )

    c = connect()

    c.execute(
        "DELETE FROM polls WHERE poll_id=?",
        (poll.poll_id,)
    )

    c.commit()
    c.close()

    session["current"] += 1

    save_session(
        user_id,
        session
    )

    await asyncio.sleep(1)

    if session["current"] >= TEST_SIZE:
        await finish(user_id)
    else:
        await send_question(user_id)


# ==============================
# FINISH
# ==============================

async def finish(user_id):

    session = load_session(
        user_id
    )

    if not session:
        return

    if session.get("finished"):
        return

    session["finished"] = True

    score = session["score"]

    percent = round(
        score / TEST_SIZE * 100
    )

    save_session(
        user_id,
        session
    )

    await bot.send_message(
        user_id,
        "🏆 TEST YAKUNLANDI!\n\n"
        f"🧬 Natija: "
        f"{score}/{TEST_SIZE}\n"
        f"📈 Foiz: {percent}%\n\n"
        "🔄 Yangi test uchun "
        "/start bosing."
    )


# ==============================
# MAIN
# ==============================

async def main():

    init_db()

    logging.info(
        "🧬 BIOLOGY BOT ISHLAYAPTI"
    )

    while True:

        try:

            await bot.delete_webhook(
                drop_pending_updates=False
            )

            await dp.start_polling(
                bot
            )

        except asyncio.CancelledError:

            break

        except Exception as e:

            logging.exception(
                "BOT TO'XTADI: %s",
                e
            )

            logging.info(
                "10 soniyadan keyin "
                "qayta ishga tushadi..."
            )

            await asyncio.sleep(10)


if __name__ == "__main__":

    asyncio.run(main())
