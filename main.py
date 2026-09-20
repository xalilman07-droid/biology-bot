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


# =========================================================
# SOZLAMALAR
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

DB_FILE = "questions.db"

TEST_SIZE = 20
BATCH_SIZE = 5

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN topilmadi!")


# =========================================================
# GEMINI
# =========================================================

ai_client = None

if GEMINI_API_KEY:
    ai_client = genai.Client(
        api_key=GEMINI_API_KEY
    )


# =========================================================
# TELEGRAM
# =========================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =========================================================
# TEST SESSIYALARI
# =========================================================

sessions = {}

poll_data = {}


# =========================================================
# DATABASE
# =========================================================

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


def normalize_question(text):

    text = str(text).lower().strip()

    for char in ".,!?;:()[]{}\"'`":
        text = text.replace(char, "")

    return " ".join(text.split())


def question_hash(text):

    return hashlib.sha256(
        normalize_question(text).encode("utf-8")
    ).hexdigest()


def is_question_used(user_id, question):

    conn = sqlite3.connect(DB_FILE)

    result = conn.execute(
        """
        SELECT 1
        FROM used_questions
        WHERE user_id = ?
        AND question_hash = ?
        """,
        (
            user_id,
            question_hash(question)
        )
    ).fetchone()

    conn.close()

    return result is not None


def save_question(user_id, question):

    conn = sqlite3.connect(DB_FILE)

    conn.execute(
        """
        INSERT OR IGNORE INTO used_questions
        (user_id, question_hash, question)
        VALUES (?, ?, ?)
        """,
        (
            user_id,
            question_hash(question),
            question
        )
    )

    conn.commit()
    conn.close()


def get_old_questions(user_id, limit=100):

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


# =========================================================
# O'XSHASHLIK
# =========================================================

def is_similar_question(
    new_question,
    old_questions,
    threshold=0.82
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

        if similarity >= threshold:
            return True

    return False


# =========================================================
# SAVOLNI TEKSHIRISH
# =========================================================

def validate_question(item):

    if not isinstance(item, dict):
        return None

    question = str(
        item.get(
            "question",
            ""
        )
    ).strip()

    options = item.get(
        "options"
    )

    correct = item.get(
        "correct_option_id"
    )

    explanation = str(
        item.get(
            "explanation",
            "To'g'ri javobning biologik izohi."
        )
    ).strip()

    if not question:
        return None

    if not isinstance(
        options,
        list
    ):
        return None

    if len(options) != 4:
        return None

    options = [
        str(option).strip()
        for option in options
    ]

    if any(
        not option
        for option in options
    ):
        return None

    if len(set(options)) != 4:
        return None

    if not isinstance(
        correct,
        int
    ):
        return None

    if correct not in [
        0,
        1,
        2,
        3
    ]:
        return None

    return {
        "question": question,
        "options": options,
        "correct_option_id": correct,
        "explanation": explanation
    }


# =========================================================
# VARIANTLARNI ARALASHTIRISH
# =========================================================

def shuffle_options(question_data):

    options = list(
        question_data["options"]
    )

    correct_id = question_data[
        "correct_option_id"
    ]

    correct_answer = options[
        correct_id
    ]

    random.shuffle(
        options
    )

    question_data["options"] = options

    question_data[
        "correct_option_id"
    ] = options.index(
        correct_answer
    )

    return question_data


# =========================================================
# JSON AJRATISH
# =========================================================

def extract_json(text):

    text = text.strip()

    if text.startswith("```"):

        text = text.replace(
            "```json",
            "",
            1
        )

        text = text.replace(
            "```",
            ""
        )

        text = text.strip()

    # ARRAY
    start = text.find("[")
    end = text.rfind("]")

    if (
        start != -1
        and end != -1
        and end > start
    ):

        return json.loads(
            text[start:end + 1]
        )

    # OBJECT
    start = text.find("{")
    end = text.rfind("}")

    if (
        start != -1
        and end != -1
        and end > start
    ):

        return json.loads(
            text[start:end + 1]
        )

    raise ValueError(
        "JSON topilmadi"
    )


# =========================================================
# GEMINI'DAN 5 TA MURAKKAB SAVOL
# =========================================================

def generate_gemini_batch(
    user_id,
    batch_size,
    current_questions
):

    if not ai_client:
        return []

    old_questions = get_old_questions(
        user_id,
        80
    )

    forbidden_questions = (
        old_questions
        + current_questions
    )

    old_text = "\n".join(
        f"- {q}"
        for q in forbidden_questions[-80:]
    )

    prompt = f"""
Sen OLIY DARAJADAGI professional
biologiya test tuzuvchisan.

Biologiyadan aynan {batch_size} ta
MURAKKAB test savoli yarat.

Bu oddiy yodlash savollari bo'lmasin.

Savollar:
- tahlil qilish
- sabab-oqibatni aniqlash
- biologik jarayonlarni taqqoslash
- vaziyatdan xulosa chiqarish
- tajriba natijasini tushunish

kabi fikrlashni talab qilsin.

Mavzularni aralashtir:

- genetika
- molekulyar biologiya
- hujayra biologiyasi
- biokimyo
- odam fiziologiyasi
- anatomiya
- o'simliklar fiziologiyasi
- mikrobiologiya
- ekologiya
- evolyutsiya

Bir xil mavzuga yopishib qolma.

HAR BIR SAVOLDA:

- aynan 4 ta variant
- faqat 1 ta to'g'ri javob
- noto'g'ri variantlar ham mantiqan ishonarli
- ilmiy jihatdan aniq
- qisqa ilmiy izoh

Quyidagi savollarni TAKRORLAMA:

{old_text}

Faqat JSON ARRAY qaytar:

[
  {{
    "question": "Savol",
    "options": [
      "Variant 1",
      "Variant 2",
      "Variant 3",
      "Variant 4"
    ],
    "correct_option_id": 0,
    "explanation": "Ilmiy izoh"
  }}
]

QOIDALAR:

- aynan {batch_size} ta savol
- correct_option_id 0, 1, 2 yoki 3
- faqat bitta javob to'g'ri
- Markdown ishlatma
- qo'shimcha matn yozma
- faqat JSON ARRAY qaytar
"""

    try:

        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        if not response.text:
            return []

        data = extract_json(
            response.text
        )

        if isinstance(
            data,
            dict
        ):
            data = [data]

        if not isinstance(
            data,
            list
        ):
            return []

        result = []

        seen = list(
            forbidden_questions
        )

        for item in data:

            question = validate_question(
                item
            )

            if not question:
                continue

            q_text = question[
                "question"
            ]

            # Aniq takror
            if is_question_used(
                user_id,
                q_text
            ):
                continue

            # O'xshash savol
            if is_similar_question(
                q_text,
                seen
            ):
                continue

            result.append(
                question
            )

            seen.append(
                q_text
            )

            if len(result) >= batch_size:
                break

        return result

    except Exception as e:

        logging.warning(
            f"Gemini batch xatosi: {e}"
        )

        return []


# =========================================================
# LOCAL SAVOLLAR
# =========================================================

def get_local_questions(
    user_id,
    needed,
    current_questions
):

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

    forbidden = (
        old_questions
        + current_questions
    )

    result = []

    for item in questions:

        question_text = item.get(
            "q"
        )

        options = item.get(
            "o"
        )

        correct = item.get(
            "c"
        )

        if not question_text:
            continue

        if not isinstance(
            options,
            list
        ):
            continue

        if len(options) != 4:
            continue

        if correct not in [
            0,
            1,
            2,
            3
        ]:
            continue

        if is_question_used(
            user_id,
            question_text
        ):
            continue

        if is_similar_question(
            question_text,
            forbidden
        ):
            continue

        question = {
            "question": question_text,

            "options": list(
                options
            ),

            "correct_option_id": correct,

            "explanation":
                item.get(
                    "e",
                    item.get(
                        "explanation",
                        "Bu savol biologiya bazasidan olindi."
                    )
                )
        }

        question = validate_question(
            question
        )

        if not question:
            continue

        result.append(
            question
        )

        forbidden.append(
            question_text
        )

        if len(result) >= needed:
            break

    return result


# =========================================================
# 20 TA TEST YARATISH
# =========================================================

async def build_test(user_id):

    test_questions = []

    # ==============================================
    # GEMINI: 5 + 5 + 5 + 5 = 20
    # ==============================================

    if ai_client:

        for batch_number in range(4):

            needed = min(
                BATCH_SIZE,
                TEST_SIZE - len(
                    test_questions
                )
            )

            if needed <= 0:
                break

            for attempt in range(3):

                batch = await asyncio.to_thread(
                    generate_gemini_batch,
                    user_id,
                    needed,
                    [
                        q["question"]
                        for q in test_questions
                    ]
                )

                if batch:

                    for question in batch:

                        q_text = question[
                            "question"
                        ]

                        duplicate = any(
                            q["question"]
                            == q_text
                            for q in test_questions
                        )

                        if duplicate:
                            continue

                        test_questions.append(
                            shuffle_options(
                                question
                            )
                        )

                    if len(batch) > 0:
                        break

                logging.info(
                    f"Gemini "
                    f"{batch_number + 1}-partiya "
                    f"urinish "
                    f"{attempt + 1}/3"
                )

    # ==============================================
    # YETISHMAGANINI LOCAL BAZADAN OLISH
    # ==============================================

    missing = (
        TEST_SIZE
        - len(test_questions)
    )

    if missing > 0:

        local_questions = await asyncio.to_thread(
            get_local_questions,
            user_id,
            missing,
            [
                q["question"]
                for q in test_questions
            ]
        )

        for question in local_questions:

            test_questions.append(
                shuffle_options(
                    question
                )
            )

    # ==============================================
    # 20 TA BO'LMASA TEST BOSHLANMAYDI
    # ==============================================

    if len(test_questions) < TEST_SIZE:

        logging.error(
            f"20 ta savol yig'ilmadi: "
            f"{len(test_questions)}/{TEST_SIZE}"
        )

        return None

    # ==============================================
    # SAVOLLAR TARTIBINI ARALASHTIRISH
    # ==============================================

    random.shuffle(
        test_questions
    )

    # ==============================================
    # DATABASEGA SAQLASH
    # ==============================================

    for question in test_questions:

        await asyncio.to_thread(
            save_question,
            user_id,
            question["question"]
        )

    return test_questions


# =========================================================
# HOZIRGI SAVOLNI YUBORISH
# =========================================================

async def send_current_question(
    user_id
):

    session = sessions.get(
        user_id
    )

    if not session:
        return

    current = session[
        "current"
    ]

    if current >= TEST_SIZE:

        await finish_test(
            user_id
        )

        return

    question_data = session[
        "questions"
    ][current]

    try:

        sent = await bot.send_poll(

            chat_id=user_id,

            question=(
                f"🧬 SAVOL "
                f"{current + 1}/{TEST_SIZE}\n\n"
                + question_data[
                    "question"
                ]
            ),

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

                "user_id":
                    user_id,

                "question_index":
                    current,

                "correct_option_id":
                    question_data[
                        "correct_option_id"
                    ],

                "explanation":
                    question_data.get(
                        "explanation",
                        ""
                    ),

                "answered":
                    False
            }

    except Exception as e:

        logging.error(
            f"Savol yuborish xatosi: {e}"
        )

        await bot.send_message(
            user_id,
            "⚠️ Savol yuborishda xatolik yuz berdi."
        )


# =========================================================
# TEST YAKUNI
# =========================================================

async def finish_test(
    user_id
):

    session = sessions.get(
        user_id
    )

    if not session:
        return

    if session.get(
        "finished"
    ):
        return

    session["finished"] = True

    score = session[
        "score"
    ]

    total = session[
        "total"
    ]

    percent = (
        round(
            score / total * 100
        )
        if total
        else 0
    )

    if percent >= 90:
        emoji = "🏆"

    elif percent >= 75:
        emoji = "🎉"

    elif percent >= 60:
        emoji = "👍"

    else:
        emoji = "📚"

    await bot.send_message(

        user_id,

        f"{emoji} TEST YAKUNLANDI!\n\n"

        f"🧬 Biologiya testi\n"

        f"📊 Natija: "
        f"{score}/{total}\n"

        f"📈 Foiz: "
        f"{percent}%\n\n"

        f"🔄 Yangi 20 ta savol uchun "
        f"/start bosing."
    )


# =========================================================
# START
# =========================================================

@dp.message(
    Command("start")
)
async def start_handler(
    message: Message
):

    user_id = message.from_user.id

    # Yangi sessiya
    sessions[user_id] = {

        "questions": [],

        "current": 0,

        "score": 0,

        "total": TEST_SIZE,

        "finished": False
    }

    await message.answer(

        "🧬 BIOLOGIYA QUIZ\n\n"

        "⏳ 20 ta murakkab savol "
        "tayyorlanmoqda...\n\n"

        "🧠 Savollar tahliliy bo'ladi.\n"

        "🎲 A/B/C/D variantlari "
        "aralashtiriladi.\n"

        "🚫 Savollar takrorlanmaydi."
    )

    try:

        questions = await build_test(
            user_id
        )

        if not questions:

            sessions.pop(
                user_id,
                None
            )

            await message.answer(

                "❌ 20 ta yangi savol "
                "tayyorlab bo'lmadi.\n\n"

                "Gemini vaqtincha javob "
                "bermagan yoki lokal bazada "
                "yetarli yangi savol qolmagan."
            )

            return

        sessions[user_id][
            "questions"
        ] = questions

        await message.answer(

            "✅ 20 TA SAVOL TAYYOR!\n\n"

            "🚀 Test boshlandi.\n\n"

            "Har bir javobdan keyin "
            "keyingi savol avtomatik chiqadi.\n\n"

            "Omad! 🧬🔥"
        )

        await send_current_question(
            user_id
        )

    except Exception as e:

        logging.exception(
            f"Test tayyorlash xatosi: {e}"
        )

        sessions.pop(
            user_id,
            None
        )

        await message.answer(

            "⚠️ Testni boshlashda "
            "xatolik yuz berdi.\n\n"

            "Birozdan keyin "
            "/start ni qayta bosing."
        )


# =========================================================
# POLL JAVOBI
# =========================================================

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

    if user_id != data[
        "user_id"
    ]:
        return

    if data[
        "answered"
    ]:
        return

    session = sessions.get(
        user_id
    )

    if not session:

        poll_data.pop(
            poll_id,
            None
        )

        return

    # Faqat joriy savol
    if data[
        "question_index"
    ] != session[
        "current"
    ]:

        return

    data[
        "answered"
    ] = True

    selected = (

        poll_answer.option_ids[0]

        if poll_answer.option_ids

        else None
    )

    correct = data[
        "correct_option_id"
    ]

    # ==============================================
    # NATIJA
    # ==============================================

    if selected == correct:

        session[
            "score"
        ] += 1

        result_text = (
            "✅ TO'G'RI JAVOB!\n\n"
        )

    else:

        result_text = (
            "❌ NOTO'G'RI JAVOB!\n\n"
        )

    result_text += (

        f"📊 Hozirgi natija: "

        f"{session['score']}/"
        f"{session['current'] + 1}\n\n"
    )

    explanation = data.get(
        "explanation",
        ""
    )

    if explanation:

        result_text += (

            "💡 IZOH:\n"

            + explanation
        )

    try:

        await bot.send_message(
            user_id,
            result_text
        )

    except Exception as e:

        logging.warning(
            f"Izoh yuborishda xato: {e}"
        )

    poll_data.pop(
        poll_id,
        None
    )

    # ==============================================
    # KEYINGI SAVOL
    # ==============================================

    session[
        "current"
    ] += 1

    await asyncio.sleep(
        1
    )

    if session[
        "current"
    ] >= TEST_SIZE:

        await finish_test(
            user_id
        )

    else:

        await send_current_question(
            user_id
        )


# =========================================================
# MAIN
# =========================================================

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
