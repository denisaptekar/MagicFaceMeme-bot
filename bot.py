import asyncio
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from fal_client import AsyncClient

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
FAL_KEY = os.getenv("FAL_KEY")

dp = Dispatcher()

user_states = {}  # {user_id: "template_name"}

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

# ====================== FAL (Flux Pro) ======================
fal_client = AsyncClient(key=FAL_KEY)

async def transform_face(photo_url: str, prompt: str):
    enhanced_prompt = (
        f"the exact same young man from the reference photo, male, "
        "identical face, same eyes, same nose, same hair, same skin tone, same age, same facial features, "
        "do not change gender, "
        f"only change clothing and overall style to: {prompt}, "
        "highly detailed, realistic, sharp focus, cinematic lighting, best quality"
    )
    
    result = await fal_client.subscribe(
        "fal-ai/flux-pro",
        arguments={
            "prompt": enhanced_prompt,
            "image_url": photo_url,
            "image_size": "square",
            "num_inference_steps": 20,
            "guidance_scale": 3.5,
            "strength": 0.82
        }
    )
    return result["images"][0]["url"]

# ====================== ГЛАВНОЕ МЕНЮ ======================
main_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [types.InlineKeyboardButton(text="🏋️ Изменить фигуру", callback_data="template_figure")],
    [types.InlineKeyboardButton(text="🎌 Аниме персонаж", callback_data="template_anime")],
    [types.InlineKeyboardButton(text="👴 Увидеть себя в старости", callback_data="template_old")],
    [types.InlineKeyboardButton(text="💼 Миллионер", callback_data="template_millionaire")],
])

# ====================== КЛАВИАТУРА ПОСЛЕ ГЕНЕРАЦИИ ======================
after_gen_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [types.InlineKeyboardButton(text="🔄 Сделать ещё одну трансформацию", callback_data="new_request")],
    [types.InlineKeyboardButton(text="🏠 Вернуться в главное меню", callback_data="back_to_menu")],
])

# ====================== СТАРТ ======================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Привет! Я — <b>MagicFace ✨</b>\n\n"
        "Выбери шаблон ниже или просто пришли своё селфи + описание.",
        parse_mode="HTML",
        reply_markup=main_keyboard
    )

# ====================== ОБРАБОТКА КНОПОК ======================
@dp.callback_query()
async def process_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    if data.startswith("template_"):
        if data == "template_figure":
            user_states[user_id] = "figure"
            text = "🏋️ **Отлично!** Хочешь изменить фигуру?\n\nПришли своё фото и напиши, какую фигуру ты хочешь увидеть (накачанный, атлетичный, худой и т.д.)"
        elif data == "template_anime":
            user_states[user_id] = "anime"
            text = "🎌 **Круто!** Хочешь стать аниме-персонажем?\n\nПришли своё фото и напиши, в какого аниме-персонажа хочешь превратиться"
        elif data == "template_old":
            user_states[user_id] = "old"
            text = "👴 **Интересно!** Хочешь увидеть себя в старости?\n\nПришли своё фото и напиши, в каком возрасте хочешь себя увидеть"
        elif data == "template_millionaire":
            user_states[user_id] = "millionaire"
            text = "💼 **Супер!** Хочешь почувствовать себя миллионером?\n\nПришли своё фото — я сделаю из тебя настоящего миллионера"

        await callback.message.edit_text(text)
        await callback.answer()

    elif data == "new_request":
        await callback.message.edit_text("🔄 Отправь новое фото и описание (или выбери шаблон ниже)", reply_markup=main_keyboard)
        await callback.answer()

    elif data == "back_to_menu":
        await callback.message.edit_text(
            "👋 Главное меню\n\nВыбери шаблон или пришли своё селфи + описание",
            reply_markup=main_keyboard
        )
        if user_id in user_states:
            del user_states[user_id]
        await callback.answer()

# ====================== ОБРАБОТКА ФОТО ======================
@dp.message()
async def handle_message(message: types.Message):
    if not message.photo:
        await message.answer("Пожалуйста, пришли своё фото")
        return

    photo = message.photo[-1]
    photo_file = await bot.get_file(photo.file_id)
    photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{photo_file.file_path}"

    user_text = message.caption or ""
    user_id = message.from_user.id

    template = user_states.get(user_id, "")
    
    if template == "figure":
        full_prompt = f"change body to {user_text}"
    elif template == "anime":
        full_prompt = f"anime style character {user_text}"
    elif template == "old":
        full_prompt = f"old version at age {user_text}"
    elif template == "millionaire":
        full_prompt = f"millionaire, rich, luxurious style {user_text}"
    else:
        full_prompt = user_text

    await message.answer("🔄 Превращаю тебя... (15–35 секунд)")

    try:
        result_url = await transform_face(photo_url, full_prompt)
        await message.answer_photo(result_url, caption="✅ Готово! ✨")
        
        # После генерации показываем удобные кнопки
        await message.answer(
            "Что делаем дальше?",
            reply_markup=after_gen_keyboard
        )
        
        # Очищаем состояние
        if user_id in user_states:
            del user_states[user_id]

    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {str(e)[:200]}")

# ====================== ЗАПУСК ======================
async def main():
    global bot
    bot = Bot(token=BOT_TOKEN)

    print("✅ MagicFace Bot запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
