import os
import asyncio
import google.generativeai as genai
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiohttp import web

# --- 1. SOZLAMALAR ---
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
MAQSADLI_GURUH_ID = int(os.getenv("GURUH_ID", "-1003706862748"))

# Xavfsizlik tekshiruvi
if not TELEGRAM_BOT_TOKEN:
    print("XATOLIK: BOT_TOKEN topilmadi!")
if not GOOGLE_API_KEY:
    print("XATOLIK: GOOGLE_API_KEY topilmadi!")

# Gemini sozlamalari
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=(
            "Siz Xorazm viloyati, Urganch shahridagi 'Madina Gullari' do'konining professional sotuvchi yordamchisiz. "
            "Mijozlarga o'zbek tilida (adabiy tilda), nihoyatda xushmuomala javob bering. "
            "Do'kon ma'lumotlari: Urganch shahri, TBS-Bank va Gidra kollej yonidagi filiallar. "
            "Telefon: +998 97 525 52 52. To'lov: Click, Payme, Naqd."
        )
    )

# --- 2. OBYEKTLAR ---
bot = None
if TELEGRAM_BOT_TOKEN:
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# --- 3. BOT MANTIQI ---
@dp.message()
async def mijoz_savoliga_javob(message: Message):
    # Faqat belgilangan guruhda va odamlardan kelgan xabarlarga javob berish
    if message.chat.id == MAQSADLI_GURUH_ID and not message.from_user.is_bot:
        if not message.text or not GOOGLE_API_KEY:
            return

        try:
            response = await model.generate_content_async(message.text)
            await message.reply(response.text)
        except Exception as e:
            print(f"Xatolik: {e}")

# --- 4. WEB SERVER ---
async def handle_ping(request):
    return web.Response(text="Bot is online")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server port {port} da ishga tushdi.")

# --- 5. MAIN ---
async def main():
    await start_web_server()
    if bot:
        me = await bot.get_me()
        print(f"Bot tayyor: @{me.username}")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    else:
        print("Bot ishga tushmadi: Token noto'g'ri!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Fatal error: {e}")
