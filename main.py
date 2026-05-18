import os
import asyncio
import aiohttp
import base64
import io
from openai import AsyncOpenAI
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiohttp import web

# --- 1. SOZLAMALAR ---
TOKEN = os.getenv("BOT_TOKEN", "").strip()
# OpenCode API kalitini kiritamiz
AI_KEY = os.getenv("OPENCODE_API_KEY") or os.getenv("OPENAI_API_KEY") or "sk-GO62qVc5tdwEsB4GnZo6KQ8T9EauZT22xttCo8sde5vXebueMV0f78jVraR1DZQe"
AI_KEY = AI_KEY.strip()

# Gemini zaxira kaliti (API muammo bo'lganda 100% bepul va cheksiz ishlashi uchun)
GEMINI_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
GEMINI_KEY = GEMINI_KEY.strip()
# Agar Render'da eski yoki bloklangan kalit qolib ketgan bo'lsa, yangi ishlaydigan kalitga majburiy almashtiramiz
if not GEMINI_KEY or "AIzaSyCcXGr" in GEMINI_KEY:
    GEMINI_KEY = "AIzaSyAcbir6NJ1tUaJlLKAblQyewd4TdJhmNcE"

# Guruh ID raqami
GURUH_ID_STR = os.getenv("GURUH_ID", "-1003706862748").strip()
GURUH_ID = int(GURUH_ID_STR)

# Model sozlamalari
MODEL_NAME = os.getenv("AI_MODEL", "minimax-m2.5-free").strip()

# --- 2. OPENAI-COMPATIBLE CLIENT (OpenCode Zen) ---
ai_client = None
if AI_KEY:
    ai_client = AsyncOpenAI(
        api_key=AI_KEY,
        base_url="https://opencode.ai/zen/v1",
        default_headers={
            "x-opencode-client": "cli"
        }
    )

# Tizim yo'riqnomasi (System Prompt)
SYSTEM_INSTRUCTION = (
    "Siz Xorazm viloyati, Urganch shahridagi 'Madina Gullari' do'konining professional sotuvchi yordamchisiz. "
    "Mijozlarga o'zbek tilida (adabiy tilda), nihoyatda xushmuomala javob bering. "
    "Do'kon ma'lumotlari:\n"
    "- Manzil: Urganch shahri.\n"
    "- 1-Filial: TBS-Bank yonida. Telefon: +998 97 525 52 52\n"
    "- 2-Filial: Gidra kollej yonida. Telefon: +998 97 504 52 52\n"
    "- Xizmatlar: Gullar va Sovg'alar, yetkazib berish (Dostavka) xizmati mavjud.\n"
    "- To'lov turlari: Click, Payme va naqd pul orqali.\n"
    "- Muhim: Karta raqami va boshqa batafsil ma'lumotlar uchun +998 97 525 52 52 raqamiga qo'ng'iroq qilishni yoki filialga murojaat qilishni ayting.\n"
    "Mijozlarga gullar tanlashda yordam bering. Javoblaringiz qisqa va samimiy bo'lsin."
)

# --- 3. ZAXIRA GEMINI API FUNKSIYASI (Kutubxonasiz - Direct HTTP Request) ---
async def generate_gemini_fallback(user_text: str, image_base64: str = None, mime_type: str = None) -> str:
    if not GEMINI_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    
    parts = []
    if image_base64 and mime_type:
        parts.append({
            "inlineData": {
                "mimeType": mime_type,
                "data": image_base64
            }
        })
    # Matn qismini qo'shamiz (caption yoki xabar matni bo'sh bo'lishi mumkinligi uchun zaxira)
    parts.append({"text": user_text or "Rasmga qarab sotuvchi sifatida chiroyli javob bering."})
    
    payload = {
        "contents": [
            {
                "parts": parts
            }
        ],
        "systemInstruction": {
            "parts": [{"text": SYSTEM_INSTRUCTION}]
        }
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=12) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    err_log = await resp.text()
                    print(f"Gemini Fallback HTTP Error {resp.status}: {err_log}")
    except Exception as e:
        print(f"Gemini Fallback Exception: {e}")
    return None

# --- 4. BOT VA DISPATCHER ---
bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()

@dp.message()
async def handle_message(message: Message):
    # Faqat belgilangan guruhdagi va odamlardan kelgan xabarlarga javob berish
    if message.chat.id == GURUH_ID and not message.from_user.is_bot:
        user_text = message.text or message.caption or ""
        
        # 1. Rasm to'g'ridan-to'g'ri xabarda kelgan yoki rasmga reply qilinganligini aniqlash
        photo = None
        if message.photo:
            photo = message.photo[-1]
        elif message.reply_to_message and message.reply_to_message.photo:
            photo = message.reply_to_message.photo[-1]
        
        # Agar na matn, na rasm bo'lmasa, qaytamiz
        if not user_text and not photo:
            return
        
        # Diagnostika uchun konsolga chiqaramiz
        print(f"!!! LOG: Xabar keldi !!! Chat ID: {message.chat.id}, Kimdan: {message.from_user.full_name}, Matn: {user_text}, Rasm: {bool(photo)}")
        
        image_base64 = None
        mime_type = None
        
        # Agar rasm bo'lsa, uni xavfsiz yuklab olib base64 formatga o'tkazamiz
        if photo and bot:
            try:
                print("Rasm yuklab olinmoqda...")
                file_info = await bot.get_file(photo.file_id)
                file_io = await bot.download_file(file_info.file_path)
                image_bytes = file_io.getvalue()
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                mime_type = "image/jpeg"
                print("Rasm muvaffaqiyatli yuklab olindi va base64 formatiga o'tkazildi.")
            except Exception as photo_err:
                print(f"Rasmni yuklashda xatolik: {photo_err}")
        
        ai_javob = None
        
        # 1-Bosqich: Agar rasm bo'lsa, to'g'ridan-to'g'ri multimodal Gemini 2.5 Flash API'dan foydalanamiz
        if image_base64:
            print("Multimodal rasm tahlili boshlandi (Gemini 2.5)...")
            ai_javob = await generate_gemini_fallback(user_text, image_base64, mime_type)
        else:
            # 2-Bosqich: Agar faqat matn bo'lsa, standart OpenCode Zen AI va Gemini fallback'dan foydalanamiz
            if ai_client:
                models_to_try = [MODEL_NAME, "big-pickle", "minimax-m2.5"]
                for current_model in models_to_try:
                    try:
                        response = await ai_client.chat.completions.create(
                            model=current_model,
                            messages=[
                                {"role": "system", "content": SYSTEM_INSTRUCTION},
                                {"role": "user", "content": user_text}
                            ],
                            max_tokens=800,
                            temperature=0.7
                        )
                        ai_javob = response.choices[0].message.content
                        print(f"AI ({current_model}) orqali muvaffaqiyatli javob berdi.")
                        break
                    except Exception as e:
                        print(f"AI Error ({current_model}): {e}")
                        continue
            
            if not ai_javob:
                print("OpenCode modellari ishlamadi yoki limit tugadi. Zaxira Gemini API ishga tushirildi...")
                ai_javob = await generate_gemini_fallback(user_text)
        
        # Javob yuborish
        if ai_javob:
            await message.reply(ai_javob)
        else:
            await message.reply("Hozirda AI xizmatida yuqori yuklama mavjud. Iltimos, birozdan so'ng qayta urinib ko'ring yoki +998 97 525 52 52 raqamiga bog'laning.")

# --- 5. RENDER UCHUN WEB SERVER ---
async def web_ping(request):
    return web.Response(text="Bot is running fine on OpenCode & Gemini Fallback!")

async def run_server():
    app = web.Application()
    app.router.add_get("/", web_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server port {port} da ishga tushdi.")

# --- 6. ASOSIY ISHGA TUSHIRISH ---
async def start_everything():
    await run_server()
    if bot:
        me = await bot.get_me()
        print(f"Bot tayyor va polling boshlandi: @{me.username} (ID: {me.id})")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    else:
        print("Xatolik: BOT_TOKEN topilmadi!")

if __name__ == "__main__":
    try:
        asyncio.run(start_everything())
    except Exception as e:
        print(f"Fatal error: {e}")
