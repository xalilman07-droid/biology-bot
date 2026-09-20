import logging
from google import genai
from google.genai import types

# Model xatolik bermasligi uchun 2026-yilgi eng yangi va barqaror modellardan foydalanamiz
MODELS_TO_TRY = [
    "gemini-2.5-flash",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro-latest"
]

async def generate_ai_question():
    """
    Gemini AI orqali biologiyaga oid yangi savol generatsiya qilish funksiyasi.
    Aksariyat modellar 404 berganda zaxira modelga o'tadi.
    """
    for model_name in MODELS_TO_TRY:
        try:
            # Client yaratish (API KEY ni osongina oladi)
            client = genai.Client()
            
            prompt = (
                "Menga biologiya fanidan 1 ta o'rta yoki murakkab darajadagi test savolini tayyorlab ber. "
                "Javob faqat va faqat quyidagi JSON formatida bo'lsin, hech qanday ortiqcha matnsiz:\n"
                '{"q": "Savol matni", "o": ["Variant A", "Variant B", "Variant C", "Variant D"], "c": 0}\n'
                "Bu yerda 'c' - to'g'ri javobning indeksi (0, 1, 2 yoki 3)."
            )

            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )

            if response and response.text:
                logging.info(f"Muvaffaqiyatli ishlatilgan model: {model_name}")
                return response.text

        except Exception as e:
            logging.warning(f"Model {model_name} xatolik berdi: {e}. Keyingi modelga o'tilmoqda...")
            continue

    logging.error("Barcha AI modellari muvaffaqiyatsiz bo'ldi. Lokal savollar bazasidan foydalanilmoqda.")
    return None
