import os
import html
import random
import logging
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from googletrans import Translator 

### Loglarni sozlash (Render'da xatoliklarni kuzatish uchun)

logging.basicConfig(level=logging.INFO) 

### Tokenni Render Environment Variables (Ekologik o'zgaruvchilar) ichidan xavfsiz o'qiymiz

BOT_TOKEN = os.getenv("BOT_TOKEN") 

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
translator = Translator() 

async def matnni_tarjima_qil(matn):
"""Inglizcha matnni o'zbek tiliga professional tarjima qilish"""
try:
tarjima = translator.translate(matn, src='en', dest='uz')
return tarjima.text
except Exception as e:
logging.error(f"Tarjimada xatolik: {e}")
return matn  # Xatolik bo'lsa, asl matnni qaytaradi 

async def googledan_murakkab_test_olish():
"""Ochiq Google/Internet bazasidan (OTDB) murakkab biologiya testi olish va tarjima qilish""" 

### Science & Nature (Biologiya) kategoriyasi, Hard (Murakkab) darajasi

url = "https://opentdb.com/api.php?amount=1&category=17&difficulty=hard&type=multiple" 

async with aiohttp.ClientSession() as session:
async with session.get(url) as response:
if response.status == 200:
data = await response.json()
if data['response_code'] == 0:
natija = data['results'] 

### Maxsus html belgilarni oddiy matnga o'giramiz

inglizcha_savol = html.unescape(natija['question'])
inglizcha_togri = html.unescape(natija['correct_answer'])
inglizcha_notogri = [html.unescape(ans) for ans in natija['incorrect_answers']] 

### O'zbek tiliga tarjima qilish bosqichi

uzb_savol = await matnni_tarjima_qil(inglizcha_savol)
uzb_togri = await matnni_tarjima_qil(inglizcha_togri)
uzb_notogri = []
for ans in inglizcha_notogri:
tarjima_ans = await matnni_tarjima_qil(ans)
uzb_notogri.append(tarjima_ans) 

### Variantlarni yig'ish va aralashtirish

variantlar = uzb_notogri + [uzb_togri]
random.shuffle(variantlar) 

            # To'g'ri javob nechanchi indeksdaligini topish
            togri_indeks = variantlar.index(uzb_togri)
            
            return {
                "savol": f"🔬 Googledan olingan murakkab biologiya testi:\n\n{uzb_savol}",
                "variantlar": variantlar,
                "togri_indeks": togri_indeks
            }

return None

@dp.message_handler(commands=['start'])
async def start_komandasi(message: types.Message):
"""Foydalanuvchi har safar start berganda mutloqo yangi test yuklanadi"""
await message.answer("Salom! Googledan siz uchun mutloqo yangi va murakkab biologiya testini qidirmoqdaman... 🔄") 

test = await googledan_murakkab_test_olish()

if test:
# Telegram Quiz rejimida yuborish
await bot.send_poll(
chat_id=message.chat.id,
question=test['savol'],
options=test['variantlar'],
type='quiz',
correct_option_id=test['togri_indeks'],
is_anonymous=False
)
else:
await message.answer("Kechirasiz, internetdan yangi test yuklashda xatolik yuz berdi. Qayta urinib ko'ring! ❌")

if **name** == '**main**': 

### Render'da fon rejimida doimiy ishlashi uchun polling ishga tushuramiz

executor.start_polling(dp, skip_updates=True)



