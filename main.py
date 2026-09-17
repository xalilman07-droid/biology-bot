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

# Render advanced bo'limidagi xavfsiz BOT_TOKENni o'qiymiz
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Xatolik: BOT_TOKEN topilmadi! Render muhitiga token kiriting.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# 2. MA'LUMOTLAR BAZASI (SQLite)
conn = sqlite3.connect("biology_bot.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, name TEXT, ball INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS active_polls (poll_id TEXT PRIMARY KEY, user_id INTEGER, quiz_index INTEGER)''')
conn.commit()

# 3. ODAM ANATOMIYASI VA SALOMATLIGIDAN MUKAMMAL TESTLAR BAZASI (35 TA PREMIUM SAVOL)
BIOLOGY_QUIZZES = [
    {
        "q": "Odam organizmida qaysi gormon qondagi kalsiy miqdorini kamaytirishga xizmat qiladi?",
        "o": ["Paratgormon", "Kalsitonin", "Tiroksin", "Aldosteron"],
        "c": 1,
        "e": "Qalqonsimon bezdan chiquvchi Kalsitonin gormoni kalsiyni qondan suyakka o'tkazib, qondagi miqdorini kamaytiradi."
    },
    {
        "q": "Yurak qorinchalari sistolasi (qisqarishi) qancha vaqt davom etadi?",
        "o": ["0.1 soniya", "0.3 soniya", "0.4 soniya", "0.8 soniya"],
        "c": 1,
        "e": "Yurak siklining 0.3 soniyasida qorinchalar qisqarib, qonni yirik qon tomirlariga (aorta va o'pka arteriyasiga) haydaydi."
    },
    {
        "q": "Nerv impulsining bitta neyrondan ikkinchisiga o'tish joyi qanday nomlanadi?",
        "o": ["Akson", "Dendrit", "Sinaps", "Medulla"],
        "c": 2,
        "e": "Sinaps — nerv oxirlarining boshqa neyron yoki ishchi organ bilan tutashgan va kimyoviy (mediator) yo'l bilan impuls o'tuvchi qismidir."
    },
    {
        "q": "Odamda miya ko'prigi va uzunchoq miya markaziy nerv tizimining qaysi qismiga kiradi?",
        "o": ["O'rta miya", "Orqa miya", "Varoliy ko'prigi", "Rombmonand (ortki) miya"],
        "c": 3,
        "e": "Uzunchoq miya va miya ko'prigi anatomik jihatdan rombmonand miya tarkibiy qismlari hisoblanadi."
    },
    {
        "q": "Odam organizmida urea (mochevina) sintezi asosan qaysi organda amalga oshadi?",
        "o": ["Buyrakda", "Jigarda", "O'pkada", "Oshqozon osti bezida"],
        "c": 1,
        "e": "Oqsillar parchalanishidan hosil bo'lgan zaharli ammiak moddasi jigarda mochevinaga aylantiriladi, buyrak esa uni shunchaki filtrlab chiqaradi."
    },
    {
        "q": "Insonda qon guruhini aniqlovchi agglyutinogenlar hujayraning qaysi qismida joylashgan?",
        "o": ["Qon plazmasida", "Eritrotsitlar membranasida", "Leykotsitlar yadrosida", "Trombotsitlarda"],
        "c": 1,
        "e": "A va B agglyutinogenlar (antigenlar) eritrotsitlar yuzasidagi tashqi membranasida joylashgan bo'ladi."
    },
    {
        "q": "Eshittirish a'zosi bo'lgan Korti organi ichki quloqning qaysi qismida joylashgan?",
        "o": ["Dahlizda", "Yarim doira naylarida", "Chig'anoqda (Salyangoz)", "Nog'ora bo'shlig'ida"],
        "c": 2,
        "e": "Ichki quloqdagi chig'anoq (cochlea) kanallari ichida tovush to'lqinlarini qabul qiluvchi reseptor hujayralardan iborat Korti organi joylashgan."
    },
    {
        "q": "Odamda ko'zning to'r pardasida (Setchatka) rangni idrok etuvchi reseptorlar qanday ataladi?",
        "o": ["Tayoqchalar", "Kolbachalar", "Neyronlar", "Xrustalik"],
        "c": 1,
        "e": "Kolbachalar (kodlar) rangli ko'rish va kunduzgi yorug'likka javob beradi. Tayoqchalar esa oq-qorani va g'ira-shira qorong'ulikni sezadi."
    },
    {
        "q": "Odam skeletida o'zaro harakatsiz birikkan suyaklar guruhini aniqlang.",
        "o": ["Umurtqalar", "Ensa va tepa suyaklari", "Yelka va bilak", "Kaft va barmoq"],
        "c": 1,
        "e": "Kalla suyagining ensa, chakka va tepa suyaklari choklar yordamida bir-biri bilan mutlaqo harakatsiz birikkan."
    },
    {
        "q": "Me'da shirasi tarkibidagi qaysi modda pepsinojen fermentini faollashtiradi va bakteriyalarni o'ldiradi?",
        "o": ["Xolat kislotasi", "Xlorid kislotasi (HCl)", "Lozotsim", "Pankreatin"],
        "c": 1,
        "e": "Me'da qoplama hujayralaridan ajraladigan xlorid kislotasi (HCl) muhitni kislotali qilib, fermentlarni faollashtiradi va dezinfeksiya qiladi."
    },
    {
        "q": "Qaysi vitamin yetishmasligi oqibatida odamda qonning ivish xususiyati pasayib ketadi?",
        "o": ["A vitamini", "C vitamini", "E vitamini", "K vitamini"],
        "c": 3,
        "e": "K vitamini jigarda prothrombin (qon ivituvchi omil) sintezlanishi uchun zarur. U yetishmasa, qon to'xtashi qiyinlashadi."
    },
    {
        "q": "Odam tanasida eng katta limfa tomiri qaysi bo'shliq bo'ylab o'tadi va qayerga quyiladi?",
        "o": ["Ko'krak yo'li, chap o'mrov osti venasiga", "Qorin yo'li, darvoza venasiga", "O'ng limfa yo'li, uyqu arteriyasiga", "Aorta yo'li, yurakka"],
        "c": 0,
        "e": "Eng yirik ko'krak limfa yo'li qorin bo'shlig'idan boshlanib, chap o'mrov osti venasiga quyiladi."
    },
    {
        "q": "Insonda nafas olish markazi bosh miyaning qaysi qismida joylashgan?",
        "o": ["O'rta miyada", "Uzunchoq miyada", "Oraliq miyada", "Miyachada"],
        "c": 1,
        "e": "Hayotiy muhim markazlar (nafas olish, qon aylanish, yutish, qusish) uzunchoq miyada joylashgan."
    },
    {
        "q": "Qon plazmasidagi qaysi oqsil immun tizimida antitanachalar (antikor) vazifasini bajaradi?",
        "o": ["Albuminlar", "Fibrinogen", "Gamma-globulinlar", "Gemoglobin"],
        "c": 2,
        "e": "Gamma-globulinlar (immunoglobulinlar) organizmga kirgan yot antigenlarni neytrallovchi himoya oqsillaridir."
    },
    {
        "q": "Ko'richakning chuvalchangsimon o'simtasi (appendiks) immun tizimida qanday organga kiradi?",
        "o": ["Markaziy organ", "Periferik limfoid organ", "Endokrin bez", "Hazm bezi"],
        "c": 1,
        "e": "Appendiks va bodomcha bezlari periferik limfoid a'zolar hisoblanib, limfotsitlar to'planishi va himoyani ta'minlaydi."
    },
    {
        "q": "Odamda qaysi parazit gijja to'g'ridan-to'g'ri o'pka alveolalarini zararlab, keyin ichakka o'tadi?",
        "o": ["Giyox qurt (Ostriki)", "Gofman qurti", "Ascaris lumbricoides (Askarida)", "Exinokokk"],
        "c": 2,
        "e": "Askarida lichinkalari qon orqali o'pka alveolalariga chiqadi, nafas yo'li orqali tomoqqa kelib, qayta yutilgach ichakda voyaga yetadi."
    },
    {
        "q": "Insonda insipid (qandsiz diabet) kasalligi qaysi gormon yetishmovchiligidan kelib chiqadi?",
        "o": ["Insulin", "Vazopressin (Antidiuretik gormon)", "Oksitotsin", "Glukagon"],
        "c": 1,
        "e": "Gipotalamusdan chiqib gipofizda saqlanuvchi Vazopressin kamayganda buyrakda suv so'rilishi buziladi va odam sutkasiga 10-15 litr suv yo'qotadi."
    },
    {
        "q": "Buyrak jomining yallig'lanishi bilan kechadigan og'ir kasallik qanday nomlanadi?",
        "o": ["Sistit", "Nefrit", "Piyelonefrit", "Uretradit"],
        "c": 2,
        "e": "Piyelonefrit — buyrak to'qimasi va buyrak jomining bakteriyalar ta'sirida yallig'lanishi hisoblanadi."
    },
    {
        "q": "Ko'z qorachig'ining kengayishi va qisqarishi qaysi nerv tizimi tomonidan boshqariladi?",
        "o": ["Faqat simpatik", "Vegetativ (Simpatik va Parasimpatik)", "Somatik nerv tizimi", "Faqat markaziy"],
        "c": 1,
        "e": "Simpatik nerv ko'z qorachig'ini kengaytiradi (qo'rqqanda), parasimpatik nerv esa toraytiradi. Bular vegetativ tizimga kiradi."
    },
    {
        "q": "Odam organizmida eritrotsitlar asosan qayerda parchalanadi?",
        "o": ["Sariq ilikda", "Taloq va jigarda", "O'pkada", "Buyrak usti bezida"],
        "c": 1,
        "e": "Qarigan va shikastlangan eritrotsitlar asosan taloqda ('eritrotsitlar qabristoni') va jigarda yo'q qilinadi."
    },
    {
        "q": "Katta qon aylanish doirasi yurakning qaysi kamerasidan boshlanadi?",
        "o": ["O'ng bo'lmacha", "O'ng qorinchadan", "Chap bo'lmachadan", "Chap qorinchadan"],
        "c": 3,
        "e": "Katta qon aylanish doirasi chap qorinchadan aorta qon tomiri bilan boshlanadi."
    },
    {
        "q": "Nafas chiqarilganda havo tarkibidagi karbonat angidrid (CO2) miqdori taxminan necha foizni tashkil etadi?",
        "o": ["0.03%", "4%", "16%", "21%"],
        "c": 1,
        "e": "Kiritilgan havoda CO2 0.03% bo'lsa, o'pkadan chiqarilgan havoda uning miqdori 4% gacha ko'payadi."
    },
    {
        "q": "Odamda tirsak va tizza bo'g'imlari anatomik tuzilishiga ko'ra qaysi turga kiradi?",
        "o": ["Yassi bo'g'imlar", "Egarsimon bo'g'imlar", "Bloksimon (oshidli) bo'g'imlar", "Sharsimon bo'g'imlar"],
        "c": 2,
        "e": "Tirsak va tizza faqat bir tomonga (bukilish va yozilish) harakatlanadigan bloksimon bo'g'imlardir."
    },
    {
        "q": "Qaysi gormon yetishmovchiligi bolalarda kretinizm (jismoniy va aqliy o'sishdan orqada qolish) kasalligini keltirib chiqaradi?",
        "o": ["O'sish gormoni (STG)", "Tiroksin", "Insulin", "Adrenalin"],
        "c": 1,
        "e": "Yoshlik davrida qalqonsimon bezdan Tiroksin gormoni kam ajralsa, moddalar almashinuvi sekinlashib, kretinizmga sabab bo'ladi."
    },
    {
        "q": "Insonda eshitish zonasi bosh miya yarimsharlari po'stlog'ining qaysi bo'lagida joylashgan?",
        "o": ["Ensa bo'lagida", "Peshona bo'lagida", "Chakka bo'lagida", "Tepa bo'lagida"],
        "c": 2,
        "e": "Ensa bo'lagida ko'rish markazi, Chakka bo'lagida esa eshitish va hid bilish markazlari joylashgan."
    },
    {
        "q": "O'pkaning hayotiy sig'imi qaysi asbob yordamida o'lchanadi?",
