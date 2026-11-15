import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    LabeledPrice, PreCheckoutQuery,
)
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
PRICE_STARS = 149
GIFT_COST_STARS = 149

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

orders = {}


class BuyFlow(StatesGroup):
    waiting_recipient = State()


@dp.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🎁 Отправить Premium другу — {PRICE_STARS} ⭐",
            callback_data="gift_premium"
        )]
    ])
    await message.answer(
        "👋 Привет!\n\n"
        "💎 <b>Telegram Premium на 1 месяц в подарок</b>\n"
        f"Цена: <b>{PRICE_STARS} ⭐</b>\n\n"
        "Как это работает:\n"
        "1. Указываете, кому подарить\n"
        "2. Оплачиваете звёздами\n"
        "3. В течение 10 минут я оформляю подарок\n"
        "4. Друг активирует Premium\n\n"
        "Нажмите кнопку ниже 👇",
        reply_markup=kb
    )


@dp.callback_query(F.data == "gift_premium")
async def ask_recipient(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BuyFlow.waiting_recipient)
    await callback.message.answer(
        "🎁 <b>Кому подарить Premium?</b>\n\n"
        "Отправьте username получателя, начиная с @\n"
        "Например: <code>@username</code>\n\n"
        "⚠️ Проверьте username — после активации подарок не отменить."
    )
    await callback.answer()


@dp.message(BuyFlow.waiting_recipient)
async def create_invoice(message: Message, state: FSMContext):
    recipient = message.text.strip()
    if not recipient.startswith("@") or len(recipient) < 4:
        await message.answer(
            "Пожалуйста, отправьте username в формате <code>@username</code>"
        )
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
        "✅ <b>Оплата получена!</b>\n\n"
        f"Получатель: <b>{recipient}</b>\n\n"
        "В течение 10 минут оформлю подарок Premium. "
        "Вы и получатель получите уведомление."
    )

    await bot.send_message(
        ADMIN_ID,
        f"💰 <b>Новая оплата — оформить подарок</b>\n\n"
        f"Покупатель: @{buyer_username} (ID <code>{message.from_user.id}</code>)\n"
        f"🎁 Получатель: <b>{recipient}</b>\n"
        f"Оплачено: {message.successful_payment.total_amount} ⭐\n"
        f"Заказ: <code>{payload}</code>\n\n"
        f"<b>Оформление:</b>\n"
        f"1. Откройте @PremiumBot\n"
        f"2. «Подарить Premium» → 1 месяц\n"
        f"3. Введите {recipient}\n"
        f"4. Оплатите {GIFT_COST_STARS} ⭐\n"
        f"5. Отметьте: /done {payload}"
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
        await message.answer(f"✅ Заказ {order_id} выполнен")
        try:
            await bot.send_message(
                orders[order_id]["user_id"],
                "🎁 <b>Подарок Premium оформлен!</b>\n\n"
                f"Premium отправлен для {orders[order_id]['recipient']}. "
                "Друг получит уведомление от Telegram."
            )
        except Exception as e:
            logging.error(f"Не смог уведомить: {e}")
    else:
        await message.answer("Заказ не найден")


@dp.message(Command("orders"))
async def list_orders(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not orders:
        await message.answer("Заказов нет")
        return
    lines = []
    for oid, o in orders.items():
        lines.append(f"• {o['status']} — @{o['username']} → {o['recipient']}")
    await message.answer("📋 Заказы:\n" + "\n".join(lines))


async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
