import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PRICE_STARS = 149
GIFT_COST_STARS = 149

# Обычные эмодзи (безопасные)
EMO_DUCK = '🦆'
EMO_STAR = '⭐'
EMO_PREMIUM = '💎'
EMO_GIFT = '🎁'
EMO_CHECK = '✅'
EMO_SUPPORT = '🆘'

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

orders = {}

class BuyFlow(StatesGroup):
    waiting_recipient = State()

class SupportFlow(StatesGroup):
    waiting_message = State()


def get_main_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"{EMO_GIFT} Купить Premium (149 ⭐)")],
            [KeyboardButton(text="📖 Инструкция"), KeyboardButton(text="🛡 Гарантии")],
            [KeyboardButton(text=f"{EMO_SUPPORT} Поддержка")],
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    return kb


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        f"{EMO_DUCK} <b>Привет, это Utya Premium!</b>\n\n"
        f"Мы продаем дешевый Telegram Premium всего за <b>{PRICE_STARS} {EMO_STAR}</b>!\n"
        "Быстро, надежно и с заботой о каждом.\n\n"
        "👇 Выбери действие в меню ниже:",
        reply_markup=get_main_keyboard()
    )


@dp.message(F.text == "📖 Инструкция")
async def cmd_help(message: Message):
    await message.answer(
        f"<b>Как это работает?</b> {EMO_PREMIUM}\n\n"
        "1. Нажми кнопку «Купить Premium».\n"
        "2. Напиши username друга, которому хочешь подарить премиум (в формате @username).\n"
        "3. Оплати 149 звезд.\n"
        "4. В течение 10 минут я оформлю подарок, и твой друг получит уведомление от Telegram.\n\n"
        f"⚠️ <i>Важно: у друга должен быть открыт профиль по ссылке, чтобы подарок дошел.</i>"
    )


@dp.message(F.text == "🛡 Гарантии")
async def cmd_guarantees(message: Message):
    await message.answer(
        f"<b>Наши гарантии</b> {EMO_CHECK}\n\n"
        "✅ Мы работаем только через официальный @PremiumBot (никаких взломов).\n"
        "✅ Среднее время выдачи — 5 минут.\n"
        "✅ Если подарок не пришел за 15 минут — напиши в Поддержку, мы вернем звезды или решим вопрос."
    )


@dp.message(F.text == f"{EMO_SUPPORT} Поддержка")
async def cmd_support(message: Message, state: FSMContext):
    await state.set_state(SupportFlow.waiting_message)
    await message.answer(
        f"{EMO_SUPPORT} <b>Напиши свой вопрос одним сообщением.</b>\n\n"
        "Опиши проблему или вопрос. Я передам его администратору, и он ответит тебе в течение 24 часов."
    )


@dp.message(SupportFlow.waiting_message)
async def process_support(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(f"{EMO_CHECK} <b>Обращение отправлено!</b>\nОжидай ответа здесь, в боте.")
    
    await bot.send_message(
        ADMIN_ID,
        f"📩 <b>Новое обращение в поддержку!</b>\n\n"
        f"От: @{message.from_user.username or 'нет'} (ID: <code>{message.from_user.id}</code>)\n\n"
        f"<b>Текст:</b>\n{message.text}\n\n"
        f"<i>Чтобы ответить, напиши команду:</i>\n"
        f"<code>/reply {message.from_user.id} твой текст</code>"
    )


@dp.message(Command("reply"))
async def admin_reply(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Использование: /reply ID текст")
        return
    
    user_id = int(args[1])
    text = args[2]
    
    try:
        await bot.send_message(
            user_id,
            f"<b>Ответ поддержки:</b>\n\n{text}",
            reply_markup=get_main_keyboard()
        )
        await message.answer(f"{EMO_CHECK} Ответ отправлен пользователю!")
    except Exception as e:
        await message.answer(f"Ошибка отправки: {e}")


@dp.message(F.text.contains("Купить Premium"))
async def ask_recipient(message: Message, state: FSMContext):
    await state.set_state(BuyFlow.waiting_recipient)
    await message.answer(
        f"{EMO_GIFT} <b>Кому подарить Premium?</b>\n\n"
        "Отправь username получателя, начиная с @\n"
        "Например: <code>@username</code>\n\n"
        "⚠️ Проверь username — после активации подарок не отменить."
    )


@dp.message(BuyFlow.waiting_recipient)
async def create_invoice(message: Message, state: FSMContext):
    recipient = message.text.strip()
    if not recipient.startswith("@") or len(recipient) < 4:
        await message.answer("Пожалуйста, отправь username в формате <code>@username</code>")
        return

    order_id = f"order_{message.from_user.id}_{int(datetime.now().timestamp())}"
    orders[order_id] = {
        "user_id": message.from_user.id,
        "username": message.from_user.username or "нет",
        "recipient": recipient,
        "status": "pending",
        "created": datetime.now().isoformat(),
    }
    await state.clear()

    await bot.send_invoice(
        chat_id=message.from_user.id,
        title="Telegram Premium (1 мес) — подарок",
        description=f"Подарок для {recipient}",
        payload=order_id,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Premium gift", amount=PRICE_STARS)],
    )


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def on_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    order = orders.get(payload)
    if order:
        order["status"] = "paid"

    recipient = order["recipient"] if order else "?"
    buyer_username = order["username"] if order else "?"

    await message.answer(
        f"{EMO_CHECK} <b>Оплата получена!</b>\n\n"
        f"Получатель: <b>{recipient}</b>\n\n"
        "В течение 10 минут оформлю подарок Premium. "
        "Вы и получатель получите уведомление.",
        reply_markup=get_main_keyboard()
    )

    await bot.send_message(
        ADMIN_ID,
        f"💰 <b>Новая оплата — оформить подарок</b>\n\n"
        f"Покупатель: @{buyer_username} (ID <code>{message.from_user.id}</code>)\n"
        f"{EMO_GIFT} Получатель: <b>{recipient}</b>\n"
        f"Оплачено: {message.successful_payment.total_amount} {EMO_STAR}\n"
        f"Заказ: <code>{payload}</code>\n\n"
        f"<b>Оформление:</b>\n"
        f"1. Открой @PremiumBot\n"
        f"2. «Подарить Premium» → 1 месяц\n"
        f"3. Введи {recipient}\n"
        f"4. Оплати {GIFT_COST_STARS} {EMO_STAR}\n"
        f"5. Отметь: /done {payload}"
    )


@dp.message(Command("done"))
async def mark_done(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /done order_id")
        return
    order_id = args[1].strip()
    if order_id in orders:
        orders[order_id]["status"] = "done"
        await message.answer(f"{EMO_CHECK} Заказ {order_id} выполнен")
        try:
            await bot.send_message(
                orders[order_id]["user_id"],
                f"{EMO_GIFT} <b>Подарок Premium оформлен!</b>\n\n"
                f"Premium отправлен для {orders[order_id]['recipient']}. "
                "Друг получит уведомление от Telegram.",
                reply_markup=get_main_keyboard()
            )
        except Exception as e:
            logging.error(f"Не смог уведомить: {e}")
    else:
        await message.answer("Заказ не найден")


async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
