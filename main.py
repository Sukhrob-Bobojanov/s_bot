import os
import asyncio
import google.generativeai as genai
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiohttp import web

# --- 1. SOZLAMALAR ---
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MAQSADLI_GURUH_ID = int(os.getenv("GURUH_ID", "-1003706862748"))

# Gemini sozlamalari
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    system_instruction=(
        "Siz Xorazm viloyati, Urganch shahridagi 'Madina Gullari' do'konining professional sotuvchi yordamchisiz. "
        "Mijozlarga o'zbek tilida (adabiy tilda), nihoyatda xushmuomala javob bering. "
        "Javoblaringiz qisqa va samimiy bo'lsin."
    )
)

# --- 2. OBYEKTLARNI ISHGA TUSHIRISH ---
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# --- 3. TELEGRAM BOT MANTIQI ---
@dp.message()
async def mijoz_savoliga_javob(message: Message):
    # DIAGNOSTIKA: HAR QANDAY XABARNI LOGGA CHIQARISH
    print(f"!!! LOG: Xabar keldi !!! Chat ID: {message.chat.id}, Kimdan: {message.from_user.full_name}, Matn: {message.text}")
    
    if not message.from_user.is_bot:
        if not message.text:
            return

        try:
            response = await model.generate_content_async(message.text)
            ai_javob = response.text
            await message.reply(ai_javob)
            print(f"AI javob berdi: {ai_javob}")
        except Exception as e:
            print(f"Gemini xatoligi: {e}")

# --- 4. WEB SERVER ---
async def handle_ping(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server {port}-portda ishga tushdi.")

# --- 5. ASOSIY ISHGA TUSHIRISH MANTIQI ---
async def main():
    await start_web_server()
    
    # Bot ma'lumotlarini tekshirish
    me = await bot.get_me()
    print(f"Bot ishga tushdi: @{me.username} (ID: {me.id})")
    
    # Webhookni tozalash (xatoliklarni oldini olish uchun)
    await bot.delete_webhook(drop_pending_updates=True)
    
    print("Telegram bot polling rejimi boshlandi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
