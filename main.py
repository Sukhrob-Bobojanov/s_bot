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
    "Siz Xorazm viloyati, Urganch shahridagi 'Madina Gullari' do'konining professional, samimiy va jonli sotuvchi yordamchisiz. "
    "Mijozlar bilan xuddi haqiqiy do'kon sotuvchisi kabi juda issiq, tabiiy va samimiy suhbat quring. "
    "QAT'IY MUHIM QOIDALAR:\n"
    "1. Har bir javobda do'kon ma'lumotlarini (manzillar, telefonlar, to'lovlar) shablon yoki nusxa kabi to'kib tashlamang! "
    "Ushbu ma'lumotlarni faqat va faqat mijoz so'ragandagina taqdim eting.\n"
    "2. Har bir xabarda qayta-qayta salomlashmang! Agar suhbat boshida salomlashib bo'lingan bo'lsa (tarixga qarang), keyingi javoblarda aslo 'Assalomu alaykum' yoki 'Va alaykum assalom' deb qayta yozmang! Suhbatni to'g'ridan-to'g'ri samimiy davom ettiring.\n"
    "3. Mijoz oldingi xabarlarida bergan ma'lumotlarini (masalan, kim uchun gul olyotganini: onasi, singlisi, rafiqasi; budjetini; sevimli gulini) suhbat tarixidan eslab qoling. Ularni aslo qaytadan so'ramang! Masalan, agar mijoz bir marta 'onamga' deb aytgan bo'lsa, keyingi xabarda 'buni kimga sovg'a qilmoqchisiz?' deb qayta so'rash qat'iyan taqiqlanadi! Muloqotni 'onajoningiz uchun' deb davom ettiring.\n"
    "4. Javoblaringiz juda qisqa (1-3 gapdan oshmasin), jonli, shirin va suhbatdoshni jalb qiladigan bo'lsin. Har doim suhbat oxirida mijozga samimiy savol berib, muloqotni davom ettiring.\n"
    "5. Agar mijoz rasm yuborsa yoki rasmga reply qilsa, rasmga e'tibor qarating, undagi mahsulotni aniq tasvirlang va unga hayrihohlik bildiring.\n"
    "6. Rasmiy va quruq gapirmang, tabiiy va chiroyli emojilardan me'yorida foydalaning.\n\n"
    "DO'KON MA'LUMOTLARI (Faqat so'ralganda ishlating):\n"
    "- Manzil: Urganch shahri.\n"
    "- 1-Filial: TBS-Bank yonida. Telefon: +998 97 525 52 52\n"
    "- 2-Filial: Gidra kollej yonida. Telefon: +998 97 504 52 52\n"
    "- Xizmatlar: Gullar, sovg'alar va yetkazib berish (Dostavka) xizmati bor.\n"
    "- To'lov: Click, Payme va naqd pul."
)

# --- 3. ZAXIRA GEMINI API FUNKSIYASI (Kutubxonasiz - Direct HTTP Request) ---
async def generate_gemini_fallback(history_messages: list, image_base64: str = None, mime_type: str = None) -> str:
    if not GEMINI_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"
    
    contents = []
    for msg in history_messages:
        role = "model" if msg["role"] in ["assistant", "model"] else "user"
        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })
    
    if image_base64 and mime_type and contents:
        # Tarixdagi oxirgi xabarga rasmni qo'shib yuboramiz
        contents[-1]["parts"].insert(0, {
            "inlineData": {
                "mimeType": mime_type,
                "data": image_base64
            }
        })
    
    payload = {
        "contents": contents,
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

# Suhbatlar xotirasi (Memory): chat_id -> list of {"role": str, "content": str}
chat_histories = {}

def get_chat_history(chat_id: int) -> list:
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []
    return chat_histories[chat_id]

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
        
        # Muloqot tarixini olamiz va yangi xabarni qo'shamiz
        history = get_chat_history(message.chat.id)
        history.append({"role": "user", "content": user_text or "[Rasm yuborildi]"})
        if len(history) > 10:
            history.pop(0)
            
        ai_javob = None
        
        # 1-Bosqich: Agar rasm bo'lsa, to'g'ridan-to'g'ri multimodal Gemini 2.5 Flash API'dan foydalanamiz
        if image_base64:
            print("Multimodal rasm tahlili boshlandi (Gemini 2.5)...")
            ai_javob = await generate_gemini_fallback(history, image_base64, mime_type)
        else:
            # 2-Bosqich: Agar faqat matn bo'lsa, standart OpenCode Zen AI va Gemini fallback'dan foydalanamiz
            if ai_client:
                models_to_try = [MODEL_NAME, "big-pickle", "minimax-m2.5"]
                for current_model in models_to_try:
                    try:
                        response = await ai_client.chat.completions.create(
                            model=current_model,
                            messages=[{"role": "system", "content": SYSTEM_INSTRUCTION}] + history,
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
                ai_javob = await generate_gemini_fallback(history)
        
        # Javob yuborish
        if ai_javob:
            # AI javobini ham muloqot tarixiga saqlaymiz
            history.append({"role": "assistant", "content": ai_javob})
            if len(history) > 10:
                history.pop(0)
            await message.reply(ai_javob)
        else:
            # Agar xatolik bo'lsa, oxirgi qo'shilgan foydalanuvchi xabarini muloqot tarixidan o'chirib turamiz
            if history:
                history.pop()
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
