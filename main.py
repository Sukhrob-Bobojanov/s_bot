import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from openai import AsyncOpenAI
from aiohttp import web

# --- 1. SOZLAMALAR (Atrof-muhit o'zgaruvchilaridan olinadi) ---
# Xavfsizlik uchun tokenlarni kod ichiga yozmaymiz, Render panelidan kiritamiz
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MAQSADLI_GURUH_ID = int(os.getenv("GURUH_ID", "0"))

# --- 2. OBYEKTLARNI ISHGA TUSHIRISH ---
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# --- 3. TELEGRAM BOT MANTIQI ---
@dp.message()
async def mijoz_savoliga_javob(message: Message):
    # Faqat belgilangan guruhdagi va odamlardan kelgan xabarlarga javob berish
    if message.chat.id == MAQSADLI_GURUH_ID and not message.from_user.is_bot:
        if not message.text:
            return

        try:
            # OpenAI API ga so'rov yuborish
            response = await ai_client.chat.completions.create(
                model="gpt-4o-mini", # Arzon va tezkor model
                messages=[
                    {
                        "role": "system", 
                        "content": (
                            "Siz Xorazm viloyati, Urganch shahridagi 'Madina Gullari' do'konining professional sotuvchi yordamchisiz. "
                            "Mijozlarga o'zbek tilida (Xorazm shevasida emas, adabiy tilda), nihoyatda xushmuomala javob bering. "
                            "Do'kon ma'lumotlari:\n"
                            "- Manzil: Urganch shahri.\n"
                            "- 1-Filial: TBS-Bank yonida. Telefon: +998 97 525 52 52\n"
                            "- 2-Filial: Gidra kollej yonida. Telefon: +998 97 504 52 52\n"
                            "- Xizmatlar: Gullar va Sovg'alar, yetkazib berish (Dostavka) xizmati mavjud.\n"
                            "Mijozlarga gullar tanlashda yordam bering, narxlarni so'rashsa filiallar bilan bog'lanishni yoki kutib turishni ayting (agar aniq narxni bilmasangiz). "
                            "Javoblaringiz qisqa va samimiy bo'lsin."
                        )
                    },
                    {"role": "user", "content": message.text}
                ],
                max_tokens=200
            )
            
            ai_javob = response.choices[0].message.content
            await message.reply(ai_javob)
            
        except Exception as e:
            print(f"OpenAI xatoligi: {e}")

# --- 4. WEB SERVER (Render uxlab qolmasligi uchun) ---
async def handle_ping(request):
    return web.Response(text="Bot is running completely fine!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render portni avtomatik beradi (PORT muhit o'zgaruvchisi orqali)
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"Web server {port}-portda ishga tushdi.")

# --- 5. ASOSIY ISHGA TUSHIRISH MANTIQI ---
async def main():
    # Web serverni fonda ishga tushiramiz
    await start_web_server()
    print("Telegram bot poling rejimi boshlandi...")
    # Botni ishga tushiramiz
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
