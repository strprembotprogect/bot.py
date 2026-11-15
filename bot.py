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

# Тарифы: (Название, Цена, Код для коллбэка)
TARIFFS = {
    "1m": {"name": "1 месяц", "price": 149, "duration": "1 мес"},
    "3m": {"name": "3 месяца", "price": 599, "duration": "3 мес"},
    "6m": {"name": "6 месяцев", "price": 999, "duration": "6 мес"},
    "12m": {"name": "12 месяцев", "price": 1499, "duration": "12 мес"},
}

# Обычные эмодзи
EMO_DUCK = '🦆'
EMO_STAR = '⭐'
EMO_PREMIUM = '💎'
EMO_GIFT = '🎁'
EMO_CHECK = '✅'
EMO_SUPPORT = '🆘'

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Простая база в памяти (в проде лучше SQLite)
orders = {}
users_db = {} # user_id: {"ref_id": None, "ref_count": 0, "balance": 0, "free_premium": False}

class BuyFlow(StatesGroup):
    waiting_recipient = State()
    waiting_confirm = State()

class SupportFlow(StatesGroup):
    waiting_message = State()


def get_main_keyboard():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=f"{EMO_GIFT} Купить Premium")],
            [KeyboardButton(text="📖 Инструкция"), KeyboardButton(text="🛡 Гарантии")],
            [KeyboardButton(text="👥 Реферальная система")],
            [KeyboardButton(text=f"{EMO_SUPPORT} Поддержка")],
        ],
        resize_keyboard=True,
        is_persistent=True
    )
    return kb


def get_tariffs_keyboard():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"1 месяц — 149 {EMO_STAR}", callback_data="buy_1m")],
        [InlineKeyboardButton(text=f"3 месяца — 599 {EMO_STAR}", callback_data="buy_3m")],
        [InlineKeyboardButton(text=f"6 месяцев — 999 {EMO_STAR}", callback_data="buy_6m")],
        [InlineKeyboardButton(text=f"12 месяцев — 1499 {EMO_STAR}", callback_data="buy_12m")],
    ])
    return kb


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    # Обработка реферальной ссылки
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        ref_id = int(args[1].replace("ref_", ""))
        if ref_id != user_id:
            if user_id not in users_db:
                users_db[user_id] = {"ref_id": ref_id, "ref_count": 0, "balance": 0, "free_premium": False}
                await bot.send_message(ref_id, f"🎉 По твоей ссылке зарегистрировался новый пользователь! Ждем его покупки.")

    if user_id not in users_db:
        users_db[user_id] = {"ref_id": None, "ref_count": 0, "balance": 0, "free_premium": False}

    await message.answer(
        f"{EMO_DUCK} <b>Добро пожаловать в Utya Premium!</b>\n\n"
        f"Дешевый Telegram Premium от <b>149 {EMO_STAR}</b>.\n"
        "Быстро, надежно, с гарантией.\n\n"
        "👇 Выбирай действие в меню или жми кнопку ниже:",
        reply_markup=get_tariffs_keyboard()
    )
    await message.answer("Главное меню:", reply_markup=get_main_keyboard())


@dp.callback_query(F.data.startswith("buy_"))
async def choose_tariff(callback: CallbackQuery, state: FSMContext):
    tariff_code = callback.data.split("_")[1]
    tariff = TARIFFS[tariff_code]
    
    await state.update_data(tariff_code=tariff_code)
    await state.set_state(BuyFlow.waiting_recipient)
    
    await callback.message.edit_text(
        f"{EMO_GIFT} <b>Выбран тариф: {tariff['name']} ({tariff['price']} {EMO_STAR})</b>\n\n"
        "Отправь username получателя, начиная с @\n"
        "Например: <code>@username</code>"
    )
    await callback.answer()


@dp.message(BuyFlow.waiting_recipient)
async def process_recipient(message: Message, state: FSMContext):
    recipient = message.text.strip()
    if not recipient.startswith("@") or len(recipient) < 4:
        await message.answer("Пожалуйста, отправь username в формате <code>@username</code>")
        return

    data = await state.get_data()
    tariff_code = data.get("tariff_code")
    tariff = TARIFFS[tariff_code]
    
    await state.update_data(recipient=recipient)
    await state.set_state(BuyFlow.waiting_confirm)

    # Подтверждение
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Все верно, оплатить", callback_data="confirm_pay")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_pay")]
    ])
    
    await message.answer(
        f"<b>Проверь данные перед оплатой:</b>\n\n"
        f"Тариф: <b>{tariff['name']}</b>\n"
        f"Получатель: <b>{recipient}</b>\n"
        f"К оплате: <b>{tariff['price']} {EMO_STAR}</b>\n\n"
        f"⚠️ <i>Убедись, что username верный. После активации подарок не отменить!</i>",
        reply_markup=kb
    )


@dp.callback_query(F.data == "cancel_pay")
async def cancel_pay(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Оплата отменена. Возвращайся, когда будешь готов!")
    await callback.answer()


@dp.callback_query(F.data == "confirm_pay")
async def confirm_pay(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    tariff_code = data.get("tariff_code")
    recipient = data.get("recipient")
    tariff = TARIFFS[tariff_code]
    user_id = callback.from_user.id
    
    order_id = f"order_{user_id}_{int(datetime.now().timestamp())}"
    orders[order_id] = {
        "user_id": user_id,
        "username": callback.from_user.username or "нет",
        "recipient": recipient,
        "tariff": tariff['name'],
        "status": "pending",
        "created": datetime.now().isoformat(),
    }
    await state.clear()
    await callback.message.delete()

    # Проверка на бесплатный премиум (рефералка)
    if users_db[user_id]["free_premium"]:
        users_db[user_id]["free_premium"] = False
        await bot.send_message(user_id, f"🎁 <b>Поздравляем! Ты используешь бесплатный Premium за 3-х друзей!</b>")
        await bot.send_message(
            ADMIN_ID,
            f"🎁 <b>БЕСПЛАТНЫЙ ЗАКАЗ (Рефералка)</b>\n"
            f"От: @{callback.from_user.username} (ID {user_id})\n"
            f"Получатель: {recipient}\n"
            f"Тариф: {tariff['name']}\n\n"
            f"<i>Оформи подарок вручную!</i>"
        )
        return

    await bot.send_invoice(
        chat_id=user_id,
        title=f"Telegram Premium ({tariff['name']}) — подарок",
        description=f"Подарок для {recipient}",
        payload=order_id,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Premium gift", amount=tariff['price'])],
    )
    await callback.answer()


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def on_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    order = orders.get(payload)
    if order:
        order["status"] = "paid"

    user_id = message.from_user.id
    recipient = order["recipient"] if order else "?"
    buyer_username = order["username"] if order else "?"
    tariff_name = order["tariff"] if order else "?"
    amount = message.successful_payment.total_amount

    # --- РЕФЕРАЛЬНАЯ СИСТЕМА ---
    if user_id in users_db and users_db[user_id]["ref_id"]:
        ref_id = users_db[user_id]["ref_id"]
        if ref_id in users_db:
            # 1. Начисляем 20% от покупки на баланс
            bonus = int(amount * 0.2)
            users_db[ref_id]["balance"] += bonus
            
            # 2. Считаем количество друзей
            users_db[ref_id]["ref_count"] += 1
            count = users_db[ref_id]["ref_count"]
            
            ref_msg = f"💰 Твой друг купил Premium! Тебе начислено <b>{bonus} {EMO_STAR}</b> (20%).\n"
            
            # 3. Проверка на 3-х друзей
            if count >= 3 and not users_db[ref_id]["free_premium"]:
                users_db[ref_id]["free_premium"] = True
                ref_msg += f"\n🎉 <b>ОГО! Ты пригласил 3-х друзей и получаешь БЕСПЛАТНЫЙ Premium на 1 месяц!</b> Напиши в поддержку, чтобы забрать его."
            
            try:
                await bot.send_message(ref_id, ref_msg)
            except:
                pass

    # --- УВЕДОМЛЕНИЕ КЛИЕНТУ ---
    await message.answer(
        f"{EMO_CHECK} <b>Оплата получена!</b>\n\n"
        f"Тариф: <b>{tariff_name}</b>\n"
        f"Получатель: <b>{recipient}</b>\n\n"
        "В течение 10 минут оформлю подарок Premium.",
        reply_markup=get_main_keyboard()
    )

    # --- УВЕДОМЛЕНИЕ АДМИНУ ---
    await bot.send_message(
        ADMIN_ID,
        f"💰 <b>Новая оплата — оформить подарок</b>\n\n"
        f"Покупатель: @{buyer_username} (ID <code>{user_id}</code>)\n"
        f"{EMO_GIFT} Получатель: <b>{recipient}</b>\n"
        f"Тариф: <b>{tariff_name}</b>\n"
        f"Оплачено: {amount} {EMO_STAR}\n"
        f"Заказ: <code>{payload}</code>\n\n"
        f"<b>Оформление в @PremiumBot:</b>\n"
        f"1. Выбери {tariff_name}\n"
        f"2. Введи {recipient}\n"
        f"3. Оплати подарок\n"
        f"4. Отметь: /done {payload}"
    )


# --- РЕФЕРАЛЬНАЯ СИСТЕМА (МЕНЮ) ---
@dp.message(F.text == "👥 Реферальная система")
async def ref_menu(message: Message):
    user_id = message.from_user.id
    if user_id not in users_db:
        users_db[user_id] = {"ref_id": None, "ref_count": 0, "balance": 0, "free_premium": False}
    
    user = users_db[user_id]
    ref_link = f"https://t.me/utyaprem_bot?start=ref_{user_id}"
    
    text = (
        f"👥 <b>Твоя реферальная система</b>\n\n"
        f"🔗 Твоя ссылка: <code>{ref_link}</code>\n\n"
        f"👫 Приглашено друзей: <b>{user['ref_count']} / 3</b>\n"
        f"💰 Твой баланс: <b>{user['balance']} {EMO_STAR}</b>\n\n"
        f"<b>Как это работает:</b>\n"
        f"• За каждого друга, купившего Premium, ты получаешь <b>20%</b> от суммы на баланс.\n"
        f"• Как только <b>3 друга</b> купят премиум, ты получаешь <b>бесплатный Premium на 1 месяц</b>!\n\n"
        f"<i>Вывод баланса — через кнопку Поддержка.</i>"
    )
    await message.answer(text)


# --- ОСТАЛЬНОЕ ---
@dp.message(F.text == "📖 Инструкция")
async def cmd_help(message: Message):
    await message.answer(
        f"<b>Как это работает?</b> {EMO_PREMIUM}\n\n"
        "1. Нажми кнопку «Купить Premium».\n"
        "2. Выбери тариф (1, 3, 6 или 12 месяцев).\n"
        "3. Напиши username друга (в формате @username).\n"
        "4. Проверь данные и оплати звезды.\n"
        "5. В течение 10 минут я оформлю подарок, и твой друг получит уведомление."
    )


@dp.message(F.text == "🛡 Гарантии")
async def cmd_guarantees(message: Message):
    await message.answer(
        f"<b>Наши гарантии</b> {EMO_CHECK}\n\n"
        "✅ Работаем только через официальный @PremiumBot.\n"
        "✅ Среднее время выдачи — 5 минут.\n"
        "✅ Если подарок не пришел за 15 минут — напиши в Поддержку, вернем звезды."
    )


@dp.message(F.text == f"{EMO_SUPPORT} Поддержка")
async def cmd_support(message: Message, state: FSMContext):
    await state.set_state(SupportFlow.waiting_message)
    await message.answer(
        f"{EMO_SUPPORT} <b>Напиши свой вопрос одним сообщением.</b>\n\n"
        "Опиши проблему или вопрос. Администратор ответит в течение 24 часов."
    )


@dp.message(SupportFlow.waiting_message)
async def process_support(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(f"{EMO_CHECK} <b>Обращение отправлено!</b>\nОжидай ответа здесь, в боте.", reply_markup=get_main_keyboard())
    
    await bot.send_message(
        ADMIN_ID,
        f"📩 <b>Новое обращение!</b>\n\n"
        f"От: @{message.from_user.username or 'нет'} (ID: <code>{message.from_user.id}</code>)\n\n"
        f"<b>Текст:</b>\n{message.text}\n\n"
        f"<i>Ответить:</i> <code>/reply {message.from_user.id} текст</code>"
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
        await bot.send_message(user_id, f"<b>Ответ поддержки:</b>\n\n{text}", reply_markup=get_main_keyboard())
        await message.answer(f"{EMO_CHECK} Ответ отправлен!")
    except Exception as e:
        await message.answer(f"Ошибка отправки: {e}")


@dp.message(F.text == f"{EMO_GIFT} Купить Premium")
async def buy_menu(message: Message):
    await message.answer(
        f"{EMO_PREMIUM} <b>Выбери тариф:</b>\n\n"
        "Чем дольше срок — тем выгоднее цена!",
        reply_markup=get_tariffs_keyboard()
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
                f"Premium ({orders[order_id]['tariff']}) отправлен для {orders[order_id]['recipient']}. "
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
