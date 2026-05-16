import os
import asyncio
import google.generativeai as genai
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiohttp import web

# --- 1. SOZLAMALAR ---
TOKEN = os.getenv("BOT_TOKEN", "").strip()
AI_KEY = (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
GURUH_ID_STR = os.getenv("GURUH_ID", "-1003706862748").strip()
GURUH_ID = int(GURUH_ID_STR)

# --- 2. AI SOZLAMASI ---
if AI_KEY:
    genai.configure(api_key=AI_KEY)
    ai_model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction="Siz 'Madina Gullari' do'koni sotuvchisisiz. Xushmuomala bo'ling."
    )

# --- 3. BOT VA DISPATCHER ---
bot = Bot(token=TOKEN) if TOKEN else None
dp = Dispatcher()

@dp.message()
async def handle_message(message: Message):
    if message.chat.id == GURUH_ID and not message.from_user.is_bot:
        if not message.text or not AI_KEY:
            return
        try:
            res = await ai_model.generate_content_async(message.text)
            await message.reply(res.text)
        except Exception as e:
            print(f"AI Error: {e}")

# --- 4. RENDER UCHUN WEB SERVER ---
async def web_ping(request):
    return web.Response(text="Online")

async def run_server():
    app = web.Application()
    app.router.add_get("/", web_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Server started on port {port}")

# --- 5. ASOSIY QISM ---
async def start_everything():
    await run_server()
    if bot:
        print("Bot polling boshlandi...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    else:
        print("Error: BOT_TOKEN is missing!")

if __name__ == "__main__":
    asyncio.run(start_everything())
