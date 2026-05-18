import os
import asyncio
from openai import AsyncOpenAI
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiohttp import web

# --- 1. SOZLAMALAR ---
TOKEN = os.getenv("BOT_TOKEN", "").strip()
# OpenCode API kalitini kiritamiz (foydalanuvchi taqdim etgan kalit standart fallback sifatida ishlatiladi)
AI_KEY = os.getenv("OPENCODE_API_KEY") or os.getenv("OPENAI_API_KEY") or "sk-GO62qVc5tdwEsB4GnZo6KQ8T9EauZT22xttCo8sde5vXebueMV0f78jVraR1DZQe"
AI_KEY = AI_KEY.strip()

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
        base_url="https://opencode.ai/zen/v1"
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

# --- 3. BOT VA DISPATCHER ---
bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()

@dp.message()
async def handle_message(message: Message):
    # Faqat belgilangan guruhdagi va odamlardan kelgan xabarlarga javob berish
    if message.chat.id == GURUH_ID and not message.from_user.is_bot:
        if not message.text or not ai_client:
            return
        
        # Diagnostika uchun kelayotgan xabarni konsolga chiqaramiz
        print(f"!!! LOG: Xabar keldi !!! Chat ID: {message.chat.id}, Kimdan: {message.from_user.full_name}, Matn: {message.text}")
        
        try:
            # OpenCode Zen orqali xabar yuborish
            response = await ai_client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": message.text}
                ],
                max_tokens=800,
                temperature=0.7
            )
            ai_javob = response.choices[0].message.content
            await message.reply(ai_javob)
            print(f"AI javob berdi: {ai_javob}")
            
        except Exception as e:
            print(f"AI Xatoligi (OpenCode): {e}")

# --- 4. RENDER UCHUN WEB SERVER ---
async def web_ping(request):
    return web.Response(text="Bot is running fine on OpenCode API!")

async def run_server():
    app = web.Application()
    app.router.add_get("/", web_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server port {port} da ishga tushdi.")

# --- 5. ASOSIY ISHGA TUSHIRISH ---
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
