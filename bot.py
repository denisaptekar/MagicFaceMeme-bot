import asyncio
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from fal_client import AsyncClient
from aiohttp_socks import ProxyConnector
from aiogram.client.session.aiohttp import AiohttpSession

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
FAL_KEY = os.getenv("FAL_KEY")
PROXY_URL = os.getenv("PROXY_URL")

# ====================== БАЗА ДАННЫХ ======================
Base = declarative_base()
engine = create_engine("sqlite:///facebot.db", echo=False)
Session = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True)
    daily_count = Column(Integer, default=0)
    last_reset = Column(DateTime, default=datetime.utcnow)
    is_premium = Column(Boolean, default=False)

Base.metadata.create_all(engine)

# ====================== FAL ======================
fal_client = AsyncClient(key=FAL_KEY)

async def transform_face(photo_url: str, prompt: str):
    result = await fal_client.subscribe(
        "fal-ai/flux/dev",
        arguments={
            "prompt": f"{prompt}, highly detailed, realistic, sharp focus, best quality",
            "image_url": photo_url,
            "image_size": "square",
            "num_inference_steps": 8,
            "guidance_scale": 3.5,
            "strength": 0.82
        }
    )
    return result["images"][0]["url"]

# ====================== СТАРТ ======================
@dp.message(Command("start"))
async def start(message: types.Message):
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔥 Накачанный парень", callback_data="muscular")],
        [types.InlineKeyboardButton(text="🎌 Аниме персонаж", callback_data="anime")],
        [types.InlineKeyboardButton(text="🤠 Ковбой", callback_data="cowboy")],
    ])
    await message.answer(
        "👋 Привет! Я — <b>MagicFace ✨</b>\n\n"
        "Отправь мне своё фото + текст, во что хочешь себя превратить.\n\n"
        "Бесплатно: 3 трансформации в день",
        parse_mode="HTML",
        reply_markup=keyboard
    )

# ====================== ОБРАБОТКА ФОТО ======================
@dp.message()
async def handle_message(message: types.Message):
    if not message.photo:
        await message.answer("Отправь мне своё фото и текст в одном сообщении")
        return

    photo = message.photo[-1]
    photo_file = await bot.get_file(photo.file_id)
    photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{photo_file.file_path}"

    user_text = message.caption or "сделай красивое фото"

    await message.answer("🔄 Превращаю тебя... (10–25 секунд)")

    try:
        result_url = await transform_face(photo_url, user_text)
        await message.answer_photo(result_url, caption="✅ Готово! ✨")
    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {str(e)[:250]}")

# ====================== ЗАПУСК ======================
async def main():
    # Создаём прокси ТОЛЬКО здесь, когда event loop уже запущен
    global bot
    if PROXY_URL:
        connector = ProxyConnector.from_url(PROXY_URL)
        session = AiohttpSession(connector=connector)
    else:
        session = AiohttpSession()

    bot = Bot(token=BOT_TOKEN, session=session)

    print("✅ MagicFace Bot запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
