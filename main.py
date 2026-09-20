import os
import json
import logging
import random
import asyncio
import sqlite3
import hashlib
from difflib import SequenceMatcher

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, PollAnswer

from google import genai
from questions import BIOLOGY_QUESTIONS


# ==============================
# LOGGING
# ==============================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)


# ==============================
# ENVIRONMENT
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")


# ==============================
# GEMINI
# ==============================

ai_client = None

if GEMINI_API_KEY:
    ai_client = genai.Client(
        api_key=GEMINI_API_KEY
    )


# ==============================
# TELEGRAM
# ==============================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ==============================
# DATABASE
# ==============================

DB_FILE = "questions.db"


def init_db():

    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS used_questions (
            user_id INTEGER NOT NULL,
            question_hash TEXT NOT NULL,
            question TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, question_hash)
        )
    """)

    conn.commit()
    conn.close()


# ==============================
# SAVOLNI TOZALASH
# ==============================

def normalize_question(text):

    text = text.lower().strip()

    for char in ".,!?;:()[]{}\"'`":

        text = text.replace(char, "")

    return " ".join(text.split())


def question_hash(text):

    clean = normalize_question(text)

    return hashlib.sha256(
        clean.encode("utf-8")
    ).hexdigest()


# ==============================
# SAVOL OLDIN BERILGANMI?
# ==============================

def is_question_used(user_id, question):

    q_hash = question_hash(question)

    conn = sqlite3.connect(DB_FILE)

    result = conn.execute(
        """
        SELECT 1
        FROM used_questions
        WHERE user_id = ?
        AND question_hash = ?
        """,
        (user_id, q_hash)
    ).fetchone()

    conn.close()

    return result is not None


# ==============================
# SAVOLNI SAQLASH
# ==============================

def save_question(user_id, question):

    q_hash = question_hash(question)

    conn = sqlite3.connect(DB_FILE)

    conn.execute(
        """
        INSERT OR IGNORE INTO used_questions
        (user_id, question_hash, question)
        VALUES (?, ?, ?)
        """,
        (
            user_id,
            q_hash,
            question
        )
    )

    conn.commit()
    conn.close()


# ==============================
# ESKI SAVOLLAR
# ==============================

def get_old_questions(
    user_id,
    limit=100
):

    conn = sqlite3.connect(DB_FILE)

    rows = conn.execute(
        """
        SELECT question
        FROM used_questions
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (
            user_id,
            limit
        )
    ).fetchall()

    conn.close()

    return [
        row[0]
        for row in rows
    ]


# ==============================
# O'XSHASHLIK
# ==============================

def is_similar_question(
    new_question,
    old_questions
):

    new_text = normalize_question(
        new_question
    )

    for old_question in old_questions:

        old_text = normalize_question(
            old_question
        )

        similarity = SequenceMatcher(
            None,
            new_text,
            old_text
        ).ratio()

        if similarity >= 0.82:

            return True

    return False


# ==============================
# GEMINI SAVOL
# ==============================

def generate_gemini_question(user_id):

    if not ai_client:
        return None

    old_questions = get_old_questions(
        user_id,
        50
    )

    old_text = "\n".join(
        f"- {q}"
        for q in old_questions
    )

    prompt = f"""
Sen professional biologiya test tuzuvchisan.

Biologiya fanidan mutlaqo yangi 1 ta test savoli yarat.

4 ta javob varianti bo'lsin.

MUHIM:

Quyidagi savollarni TAKRORLAMA:

{old_text}

Yangi savol yuqoridagi savollardan
mazmunan ham farq qilishi kerak.

Faqat JSON formatida javob ber:

{{
  "question": "Savol matni",
  "options": [
    "1-variant",
    "2-variant",
    "3-variant",
    "4-variant"
  ],
  "correct_option_id": 0,
  "explanation": "To'g'ri javobning qisqa ilmiy izohi"
}}

Qoidalar:

- options aynan 4 ta
- correct_option_id 0,1,2 yoki 3
- biologiya fanidan bo'lsin
- ilmiy jihatdan to'g'ri bo'lsin
- savol oldingi savollarga o'xshamasin
- Markdown ishlatma
- faqat JSON qaytar
"""

    models = [
        "gemini-2.5-flash",
        "gemini-1.5-flash"
    ]

    for model_name in models:

        try:

            response = ai_client.models.generate_content(
                model=model_name,
                contents=prompt
            )

            if not response.text:
                continue

            text = response.text.strip()

            if text.startswith("```"):

                text = text.replace(
                    "```json",
                    ""
                )

                text = text.replace(
                    "```",
                    ""
                )

                text = text.strip()

            data = json.loads(text)

            question = data.get(
                "question"
            )

            options = data.get(
                "options"
            )

            correct = data.get(
                "correct_option_id"
            )

            explanation = data.get(
                "explanation",
                "To'g'ri javob biologik jihatdan shu variant hisoblanadi."
            )

            if not question:
                continue

            if not isinstance(
                options,
                list
            ):
                continue

            if len(options) != 4:
                continue

            if correct not in [
                0, 1, 2, 3
            ]:
                continue

            # Aniq takror
            if is_question_used(
                user_id,
                question
            ):

                logging.warning(
                    "Gemini eski savolni qaytardi."
                )

                continue

            # O'xshash savol
            if is_similar_question(
                question,
                old_questions
            ):

                logging.warning(
                    "Gemini o'xshash savol yaratdi."
                )

                continue

            return {
                "question": question,
                "options": options,
                "correct_option_id": correct,
                "explanation": explanation
            }

        except Exception as e:

            logging.warning(
                f"{model_name} xatosi: {e}"
            )

    return None


# ==============================
# LOKAL SAVOLLAR
# ==============================

def get_local_question(user_id):

    questions = list(
        BIOLOGY_QUESTIONS
    )

    random.shuffle(
        questions
    )

    old_questions = get_old_questions(
        user_id,
        5000
    )

    for item in questions:

        # Sening questions.py format:
        question = item.get("q")
        options = item.get("o")
        correct = item.get("c")

        if not question:
            continue

        if not options:
            continue

        if correct not in [
            0, 1, 2, 3
        ]:
            continue

        # Takror savol
        if is_question_used(
            user_id,
            question
        ):

            continue

        # O'xshash savol
        if is_similar_question(
            question,
            old_questions
        ):

            continue

        return {
            "question": question,
            "options": options,
            "correct_option_id": correct,
            "explanation":
                "Bu savol lokal biologiya bazasidan olindi."
        }

    return None


# ==============================
# YANGI SAVOL
# ==============================

async def get_new_question(user_id):

    # Avval Gemini
    if ai_client:

        for attempt in range(5):

            question = await asyncio.to_thread(
                generate_gemini_question,
                user_id
            )

            if question:

                save_question(
                    user_id,
                    question["question"]
                )

                return question

            logging.info(
                f"Gemini urinish: {attempt + 1}/5"
            )

    # Gemini ishlamasa lokal baza
    question = await asyncio.to_thread(
        get_local_question,
        user_id
    )

    if question:

        save_question(
            user_id,
            question["question"]
        )

        return question

    return None


# ==============================
# POLL MA'LUMOTLARI
# ==============================

poll_data = {}


# ==============================
# START
# ==============================

@dp.message(Command("start"))
async def start_handler(
    message: Message
):

    user_id = message.from_user.id

    logging.info(
        f"Yangi test: {user_id}"
    )

    question_data = await get_new_question(
        user_id
    )

    if not question_data:

        await message.answer(
            "⚠️ Yangi savol topilmadi.\n\n"
            "Birozdan keyin /start ni qayta bosing."
        )

        return

    try:

        sent = await message.answer_poll(

            question=question_data[
                "question"
            ],

            options=question_data[
                "options"
            ],

            type="quiz",

            correct_option_id=
                question_data[
                    "correct_option_id"
                ],

            is_anonymous=False
        )

        if sent.poll:

            poll_data[
                sent.poll.id
            ] = {

                "user_id": user_id,

                "explanation":
                    question_data.get(
                        "explanation",
                        ""
                    ),

                "correct_option_id":
                    question_data[
                        "correct_option_id"
                    ]
            }

    except Exception as e:

        logging.error(
            f"Poll yuborish xatosi: {e}"
        )

        await message.answer(
            "⚠️ Savol yuborishda xatolik yuz berdi."
        )


# ==============================
# JAVOBGA IZOH
# ==============================

@dp.poll_answer()
async def poll_answer_handler(
    poll_answer: PollAnswer
):

    poll_id = poll_answer.poll_id

    data = poll_data.get(
        poll_id
    )

    if not data:
        return

    user_id = poll_answer.user.id

    selected = (
        poll_answer.option_ids[0]
        if poll_answer.option_ids
        else None
    )

    correct = data[
        "correct_option_id"
    ]

    explanation = data.get(
        "explanation",
        ""
    )

    if selected == correct:

        text = "✅ To'g'ri javob!\n\n"

    else:

        text = "❌ Noto'g'ri javob.\n\n"

    if explanation:

        text += (
            "💡 Izoh:\n"
            + explanation
        )

    try:

        await bot.send_message(
            user_id,
            text
        )

    except Exception as e:

        logging.warning(
            f"Izoh yuborishda xato: {e}"
        )


# ==============================
# MAIN
# ==============================

async def main():

    init_db()

    logging.info(
        "🧬 BIOLOGY BOT ISHLAYAPTI"
    )

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    await dp.start_polling(
        bot
    )


if __name__ == "__main__":

    asyncio.run(main())
