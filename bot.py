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
PAYMENT_TOKEN = os.getenv("PAYMENT_TOKEN")  # ← добавь в .env

dp = Dispatcher()

user_states = {}  # для шаблонов

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
    referred_by = Column(Integer, nullable=True)   # кто пригласил

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
    user_id = message.from_user.id
    session = Session()
    user = session.query(User).filter_by(user_id=user_id).first()

    if not user:
        user = User(user_id=user_id, referral_code=str(uuid.uuid4())[:8])
        session.add(user)
        session.commit()

    # Если пришёл по реферальной ссылке
    if message.text and len(message.text.split()) > 1:
        ref_code = message.text.split()[1]
        referrer = session.query(User).filter_by(referral_code=ref_code).first()
        if referrer and referrer.user_id != user_id:
            user.referred_by = referrer.user_id
            # Даём +5 генераций пригласившему
            referrer.daily_count = max(0, referrer.daily_count - 5)
            session.commit()

    session.close()

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

    if data.startswith("template_"):
        # ... (шаблоны оставляем как были)
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
        await callback.answer()

    elif data == "referral":
        session = Session()
        user = session.query(User).filter_by(user_id=user_id).first()
        ref_link = f"https://t.me/MagicFaceMeme_bot?start={user.referral_code}"
        await callback.message.edit_text(
            f"🎁 <b>Твоя реферальная ссылка:</b>\n\n"
            f"{ref_link}\n\n"
            "Поделись ей с друзьями — и за каждого, кто начнёт пользоваться, ты получишь +5 дополнительных генераций!",
            parse_mode="HTML"
        )
        session.close()
        await callback.answer()

    elif data == "buy_premium":
        await callback.message.answer_invoice(
            title="Премиум-подписка MagicFace",
            description="Неограниченные генерации на 30 дней",
            payload="premium_month",
            provider_token=PAYMENT_TOKEN,
            currency="RUB",
            prices=[types.LabeledPrice(label="Премиум 30 дней", amount=59900)]  # 599 ₽
        )
        await callback.answer()

    elif data in ["new_request", "back_to_menu"]:
        # ... (остальная логика без изменений)
        if data == "new_request":
            await callback.message.edit_text("🔄 Отправь новое фото и описание", reply_markup=main_keyboard)
        else:
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
        return

    # ... (остальная логика генерации без изменений)
    # После успешной генерации:
    await message.answer("Что делаем дальше?", reply_markup=after_gen_keyboard)

# ====================== ПЛАТЕЖИ ЮKASSA ======================
@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(lambda message: message.successful_payment)
async def successful_payment(message: types.Message):
    user_id = message.from_user.id
    session = Session()
    user = session.query(User).filter_by(user_id=user_id).first()
    if user:
        user.is_premium = True
        session.commit()
    session.close()

    await message.answer(
        "🎉 Поздравляем! Премиум-подписка активирована.\n\n"
        "Теперь у тебя **неограниченное** количество генераций!"
    )

# ====================== ЗАПУСК ======================
async def main():
    global bot
    bot = Bot(token=BOT_TOKEN)

    print("✅ MagicFace Bot запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
