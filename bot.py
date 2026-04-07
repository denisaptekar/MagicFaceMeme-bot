import asyncio
import os
import uuid
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, Boolean, DateTime, String
from sqlalchemy.orm import sessionmaker, declarative_base
from fal_client import AsyncClient

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
FAL_KEY = os.getenv("FAL_KEY")
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")

dp = Dispatcher()
user_states = {}

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
    referral_code = Column(String, unique=True, nullable=True)

Base.metadata.create_all(engine)

# ====================== FAL ======================
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

# ====================== КЛАВИАТУРЫ ======================
main_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [types.InlineKeyboardButton(text="🏋️ Изменить фигуру", callback_data="template_figure")],
    [types.InlineKeyboardButton(text="🎌 Аниме персонаж", callback_data="template_anime")],
    [types.InlineKeyboardButton(text="👴 Увидеть себя в старости", callback_data="template_old")],
    [types.InlineKeyboardButton(text="💼 Миллионер", callback_data="template_millionaire")],
    [types.InlineKeyboardButton(text="🎁 Реферальная программа", callback_data="referral")],
    [types.InlineKeyboardButton(text="💰 Купить премиум", callback_data="buy_premium")],
])

back_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [types.InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_menu")]
])

after_gen_keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
    [types.InlineKeyboardButton(text="🔄 Сделать ещё одну", callback_data="new_request")],
    [types.InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")],
])

# ====================== СТАРТ ======================
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "👋 Привет! Я — <b>MagicFace ✨</b>\n\n"
        "Отправь мне своё селфи + текст, во что хочешь себя превратить.\n\n"
        "<b>Бесплатно:</b> 3 трансформации в день\n\n"
        "🎁 <b>Реферальная программа:</b> Приведи друга — и получи +5 дополнительных генераций!",
        parse_mode="HTML",
        reply_markup=main_keyboard
    )

# ====================== ОБРАБОТКА КНОПОК ======================
@dp.callback_query()
async def process_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    session = Session()
    user = session.query(User).filter_by(user_id=user_id).first()
    if not user:
        user = User(user_id=user_id, referral_code=str(uuid.uuid4())[:8])
        session.add(user)
        session.commit()

    if data.startswith("template_"):
        if data == "template_figure":
            user_states[user_id] = "figure"
            text = "🏋️ **Отлично!** Хочешь изменить фигуру?\n\nПришли своё фото и напиши, какую фигуру ты хочешь увидеть"
        elif data == "template_anime":
            user_states[user_id] = "anime"
            text = "🎌 **Круто!** Хочешь стать аниме-персонажем?\n\nПришли своё фото и я сделаю из тебя аниме-персонажа"
        elif data == "template_old":
            user_states[user_id] = "old"
            text = "👴 **Интересно!** Хочешь увидеть себя в старости?\n\nПришли своё фото и напиши, в каком возрасте хочешь себя увидеть"
        elif data == "template_millionaire":
            user_states[user_id] = "millionaire"
            text = "💼 **Супер!** Хочешь почувствовать себя миллионером?\n\nПришли своё фото — я сделаю из тебя настоящего миллионера"

        await callback.message.edit_text(text, reply_markup=back_keyboard)

    elif data == "referral":
        ref_link = f"https://t.me/MagicFaceMeme_bot?start={user.referral_code}"
        await callback.message.edit_text(
            f"🎁 <b>Твоя реферальная ссылка:</b>\n\n"
            f"{ref_link}\n\n"
            "Поделись ей с друзьями — и за каждого, кто начнёт пользоваться, ты получишь +5 дополнительных генераций!",
            parse_mode="HTML",
            reply_markup=back_keyboard
        )

    elif data == "buy_premium":
        await callback.message.answer_invoice(
            title="Премиум-подписка MagicFace",
            description="Неограниченные генерации на 30 дней",
            payload="premium_month",
            provider_token=PAYMENT_TOKEN,
            currency="RUB",
            prices=[types.LabeledPrice(label="Премиум 30 дней", amount=59900)]
        )
        await callback.message.answer("💳 Оплата открыта.\nЕсли передумал — нажми ниже:", reply_markup=back_keyboard)

    elif data == "back_to_menu":
        await callback.message.edit_text(
            "👋 Главное меню\n\nВыбери шаблон или пришли своё селфи + описание",
            reply_markup=main_keyboard
        )
        if user_id in user_states:
            del user_states[user_id]

    elif data == "new_request":
        await callback.message.edit_text("🔄 Отправь новое фото и описание", reply_markup=main_keyboard)

    session.close()
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
        await message.answer("Что делаем дальше?", reply_markup=after_gen_keyboard)
        
        if user_id in user_states:
            del user_states[user_id]

    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {str(e)[:200]}")

# ====================== ПЛАТЕЖИ ======================
@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(lambda message: message.successful_payment)
async def successful_payment(message: types.Message):
    await message.answer("🎉 Премиум-подписка активирована!")

# ====================== ЗАПУСК ======================
async def main():
    global bot
    bot = Bot(token=BOT_TOKEN)
    print("✅ MagicFace Bot запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
