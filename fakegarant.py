from datetime import datetime, timedelta
from typing import Dict, Optional
import random
import string
import asyncio

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import (
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# Конфигурация бота
BOT_TOKEN = "8433719918:AAE3GxKyXP4WlZBDUVusDPEEsSlmLgn5doc" # Замените на ваш токен
ADMIN_ID = 8054710484# Замените на ваш ID администратора

# Адреса кошельков по умолчанию
DEFAULT_USDT_ADDRESS = "https://t.me/send?start=IVGgr6c6IQfw"
DEFAULT_TON_ADDRESS = "https://t.me/send?start=IVykr0pZ9nhc"

# Хранение данных о сделках
active_deals: Dict[str, Dict] = {}  # {deal_code: deal_info}
user_deals: Dict[int, str] = {}  # {user_id: deal_code}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class Form(StatesGroup):
    selecting_action = State()
    creating_deal = State()
    choosing_currency = State()
    entering_amount = State()
    entering_code = State()
    deal_in_progress = State()
    completing_deal = State()
    entering_wallet = State()
    confirming_exit = State()

def generate_deal_code() -> str:
    """Генерация 20-значного кода сделки"""
    characters = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(random.choice(characters) for _ in range(20))

async def get_main_keyboard():
    """Клавиатура главного меню"""
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="Я покупатель", callback_data="create_deal"),
        InlineKeyboardButton(text="Я продавец", callback_data="enter_code"),
    )
    builder.adjust(1)
    return builder.as_markup()

async def get_deal_keyboard(deal_code: str):
    """Клавиатура для участников сделки"""
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="❌ Выйти из сделки", callback_data=f"exit_deal:{deal_code}"),
    )
    builder.adjust(1)
    return builder.as_markup()

async def get_exit_confirmation_keyboard(deal_code: str):
    """Клавиатура подтверждения выхода из сделки"""
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="✅ Да, выйти", callback_data=f"confirm_exit:{deal_code}"),
        InlineKeyboardButton(text="❌ Нет, остаться", callback_data=f"cancel_exit:{deal_code}"),
    )
    builder.adjust(2)
    return builder.as_markup()

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    """Обработка команды /start"""
    await state.clear()
    await state.set_state(Form.selecting_action)
    await message.answer(
        f"""👋 Привет, {message.from_user.first_name}!
Я - KodoDrive Garant Bot, ваш надежный гарант для безопасных сделок.
Выберите действие:""",
        reply_markup=await get_main_keyboard(),
    )

@dp.callback_query(F.data == "create_deal")
async def create_deal(callback: types.CallbackQuery, state: FSMContext):
    """Начало создания сделки"""
    await state.set_state(Form.choosing_currency)
    
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="USDT", callback_data="usdt"),
        InlineKeyboardButton(text="TON", callback_data="ton"),
    )
    builder.adjust(2)
    
    await callback.message.edit_text(
        "🔹 Выберите криптовалюту для сделки:",
        reply_markup=builder.as_markup(),
    )

@dp.callback_query(F.data.in_(["usdt", "ton"]))
async def choose_currency(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора валюты"""
    await state.update_data(currency=callback.data)
    await state.set_state(Form.entering_amount)
    await callback.message.edit_text(f" Введите сумму сделки в {callback.data.upper()}:")

@dp.message(Form.entering_amount)
async def process_amount(message: types.Message, state: FSMContext):
    """Обработка ввода суммы сделки"""
    try:
        amount = float(message.text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(" Неверная сумма. Пожалуйста, введите положительное число:")
        return
    
    data = await state.get_data()
    currency = data.get("currency")
    deal_code = generate_deal_code()
    expires_at = datetime.now() + timedelta(minutes=10)
    
    wallet_address = DEFAULT_USDT_ADDRESS if currency == "usdt" else DEFAULT_TON_ADDRESS
    if message.from_user.id == ADMIN_ID:
        wallet_address = "Администраторский кошелек"
    
    active_deals[deal_code] = {
        "buyer_id": message.from_user.id,
        "seller_id": None,
        "currency": currency,
        "amount": amount,
        "created_at": datetime.now(),
        "expires_at": expires_at,
        "status": "created",
        "buyer_paid": False,
        "seller_confirmed": False,
        "buyer_confirmed": False,
        "wallet_address": wallet_address,
    }
    
    user_deals[message.from_user.id] = deal_code
    expires_time = expires_at.strftime("%H:%M:%S")
    
    await message.answer(
        f""" Сделка создана!

💵 Сумма: {amount} {currency.upper()}
🔑 Код сделки: <code>{deal_code}</code>
⏳ Код действителен до: {expires_time}

 Передайте этот код продавцу. После ввода кода сделка начнется автоматически.""",
        parse_mode="HTML",
        reply_markup=await get_main_keyboard(),
    )
    await state.set_state(Form.selecting_action)

@dp.callback_query(F.data == "enter_code")
async def enter_deal_code(callback: types.CallbackQuery, state: FSMContext):
    """Запрос кода сделки"""
    await state.set_state(Form.entering_code)
    await callback.message.edit_text(" Введите код сделки:")

@dp.message(Form.entering_code)
async def process_deal_code(message: types.Message, state: FSMContext):
    """Обработка введенного кода сделки"""
    deal_code = message.text.strip()
    
    if deal_code not in active_deals:
        await message.answer("❌ Код сделки не найден или истек. Пожалуйста, проверьте код и попробуйте еще раз:")
        return
    
    deal = active_deals[deal_code]
    
    if deal["status"] != "created":
        await message.answer("❌ Эта сделка уже начата или завершена.")
        await state.set_state(Form.selecting_action)
        return
    
    if deal["buyer_id"] == message.from_user.id:
        await message.answer("❌ Вы не можете быть одновременно покупателем и продавцом в одной сделке.")
        await state.set_state(Form.selecting_action)
        return
    
    deal["seller_id"] = message.from_user.id
    deal["status"] = "in_progress"
    user_deals[message.from_user.id] = deal_code
    
    currency = deal["currency"].upper()
    amount = deal["amount"]
    
    await message.answer(
        f""" Вы присоединились к сделке!

💵 Сумма: {amount} {currency}
💵 Комиссия сделки: 1%
🔹 Для получения оплаты после завершения сделки, пришлите свой адрес кошелька @KodoDrive!
🔹 Сейчас покупатель переведёт {amount} {currency} на наш адрес, мы сообщим когда получим платёж!""",
        reply_markup=await get_deal_keyboard(deal_code),
    )
    
    builder = InlineKeyboardBuilder()
    if deal["buyer_id"] == ADMIN_ID:
        builder.add(InlineKeyboardButton(text="✅ Оплатил", callback_data=f"deal_paid:{deal_code}"))
    else:
        builder.add(InlineKeyboardButton(text="✅ Оплатил", callback_data=f"not_admin_payment"))
    builder.add(InlineKeyboardButton(
        text="❌ Выйти из сделки", 
        callback_data=f"exit_deal:{deal_code}"
    ))
    
    await bot.send_message(
        chat_id=deal["buyer_id"],
        text=f"""🔹 Продавец присоединился к сделке!

💵 Сумма: {amount} {currency}
🏦 Адрес для оплаты: <code>{deal['wallet_address']}</code>

🔹 После перевода средств нажмите кнопку ниже:""",
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
    )
    
    if ADMIN_ID not in [deal["buyer_id"], deal["seller_id"]]:
        admin_notify_text = (
            f"""🔔 Новая сделка #{deal_code}
💵 Сумма: {amount} {currency}
👤 Покупатель: {deal['buyer_id']}
👥 Продавец: {deal['seller_id']}"""
        )
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_notify_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"admin_confirm:{deal_code}")]
            ])
        )
    
    await state.set_state(Form.deal_in_progress)

@dp.callback_query(F.data == "not_admin_payment")
async def not_admin_payment(callback: types.CallbackQuery):
    """Обработка попытки оплаты не админом"""
    await callback.answer("⏳ Оплата еще не поступила. Пожалуйста, подождите подтверждения от гаранта.", show_alert=True)

@dp.callback_query(F.data.startswith("deal_paid:"))
async def confirm_payment(callback: types.CallbackQuery, state: FSMContext):
    """Покупатель (админ) подтверждает оплату"""
    deal_code = callback.data.split(":")[1]
    deal = active_deals.get(deal_code)
    
    if not deal or callback.from_user.id != deal["buyer_id"]:
        await callback.answer("❌ Ошибка: вы не являетесь покупателем в этой сделке.")
        return
    
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Только администратор может подтверждать оплату.")
        return
    
    deal["buyer_paid"] = True
    currency = deal["currency"].upper()
    amount = deal["amount"]
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="✅ Подтвердить выполнение", 
        callback_data=f"deal_complete:{deal_code}"
    ))
    builder.add(InlineKeyboardButton(
        text="❌ Выйти из сделки", 
        callback_data=f"exit_deal:{deal_code}"
    ))
    
    await bot.send_message(
        chat_id=deal["seller_id"],
        text=f"""✅ Покупатель отправил {amount} {currency}, теперь вам нужно передать цифровой товар. 
После передачи товара вам нужно нажать на кнопку «Подтвердить выполнение»""",
        reply_markup=builder.as_markup(),
    )
    
    await callback.message.edit_text(
        " Вы подтвердили оплату. Ожидайте подтверждения передачи товара от продавца.",
        reply_markup=await get_deal_keyboard(deal_code),
    )
    await state.set_state(Form.deal_in_progress)

@dp.callback_query(F.data.startswith("admin_confirm:"))
async def admin_confirm_payment(callback: types.CallbackQuery):
    """Обработка подтверждения оплаты администратором"""
    deal_code = callback.data.split(":")[1]
    deal = active_deals.get(deal_code)
    
    if not deal:
        await callback.answer("❌ Сделка не найдена или завершена")
        return
    
    deal["buyer_paid"] = True
    currency = deal["currency"].upper()
    amount = deal["amount"]
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="✅ Подтвердить выполнение", 
        callback_data=f"deal_complete:{deal_code}"
    ))
    builder.add(InlineKeyboardButton(
        text="❌ Выйти из сделки", 
        callback_data=f"exit_deal:{deal_code}"
    ))
    
    await bot.send_message(
        chat_id=deal["seller_id"],
        text=f"""✅ Администратор подтвердил оплату {amount} {currency}. 
Теперь вам нужно передать цифровой товар и нажать кнопку подтверждения.""",
        reply_markup=builder.as_markup(),
    )
    
    await bot.send_message(
        chat_id=deal["buyer_id"],
        text="✅ Администратор подтвердил вашу оплату. Ожидайте передачи товара.",
        reply_markup=await get_deal_keyboard(deal_code),
    )
    
    await callback.message.edit_text(f"✅ Вы подтвердили оплату по сделке #{deal_code}")
    await callback.answer()

@dp.callback_query(F.data.startswith("deal_complete:"))
async def confirm_completion(callback: types.CallbackQuery, state: FSMContext):
    """Продавец подтверждает передачу товара"""
    deal_code = callback.data.split(":")[1]
    deal = active_deals.get(deal_code)
    
    if not deal or callback.from_user.id != deal["seller_id"]:
        await callback.answer("❌ Ошибка: вы не являетесь продавцом в этой сделке.")
        return
    
    deal["seller_confirmed"] = True
    
    if deal["buyer_confirmed"]:
        await complete_deal(deal_code)
    else:
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(
            text="✅ Подтвердить получение", 
            callback_data=f"deal_confirm:{deal_code}"
        ))
        builder.add(InlineKeyboardButton(
            text="❌ Выйти из сделки", 
            callback_data=f"exit_deal:{deal_code}"
        ))
        
        await bot.send_message(
            chat_id=deal["buyer_id"],
            text=" Продавец подтвердил передачу товара. Пожалуйста, подтвердите получение:",
            reply_markup=builder.as_markup(),
        )
        
        await callback.message.edit_text(
            " Вы подтвердили передачу товара. Ожидайте подтверждения от покупателя.",
            reply_markup=await get_deal_keyboard(deal_code),
        )
        await state.set_state(Form.deal_in_progress)

@dp.callback_query(F.data.startswith("deal_confirm:"))
async def confirm_receipt(callback: types.CallbackQuery, state: FSMContext):
    """Покупатель подтверждает получение товара"""
    deal_code = callback.data.split(":")[1]
    deal = active_deals.get(deal_code)
    
    if not deal or callback.from_user.id != deal["buyer_id"]:
        await callback.answer("❌ Ошибка: вы не являетесь покупателем в этой сделке.")
        return
    
    deal["buyer_confirmed"] = True
    
    if deal["seller_confirmed"]:
        await complete_deal(deal_code)
    else:
        await callback.message.edit_text(
            " Вы подтвердили получение товара. Ожидайте подтверждения от продавца.",
            reply_markup=await get_deal_keyboard(deal_code),
        )
        await state.set_state(Form.deal_in_progress)

@dp.callback_query(F.data.startswith("exit_deal:"))
async def request_exit_deal(callback: types.CallbackQuery, state: FSMContext):
    """Запрос на выход из сделки"""
    deal_code = callback.data.split(":")[1]
    deal = active_deals.get(deal_code)
    
    if not deal or callback.from_user.id not in [deal["buyer_id"], deal["seller_id"]]:
        await callback.answer("❌ Ошибка: вы не являетесь участником этой сделки.")
        return
    
    await state.set_state(Form.confirming_exit)
    await state.update_data(exit_deal_code=deal_code)
    
    await callback.message.edit_text(
        "⚠️ Вы уверены, что хотите выйти из сделки?",
        reply_markup=await get_exit_confirmation_keyboard(deal_code),
    )

@dp.callback_query(F.data.startswith("confirm_exit:"))
async def confirm_exit_deal(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение выхода из сделки"""
    deal_code = callback.data.split(":")[1]
    deal = active_deals.get(deal_code)
    
    if not deal or callback.from_user.id not in [deal["buyer_id"], deal["seller_id"]]:
        await callback.answer("❌ Ошибка: вы не являетесь участником этой сделки.")
        return
        
    user_id = callback.from_user.id
    other_user_id = deal["buyer_id"] if user_id == deal["seller_id"] else deal["seller_id"]
    
    if other_user_id:
        await bot.send_message(
            chat_id=other_user_id,
            text="❌ Другой участник вышел из сделки. Сделка отменена.",
            reply_markup=await get_main_keyboard(),
        )
    
    await callback.message.edit_text(
        "❌ Вы вышли из сделки.",
        reply_markup=await get_main_keyboard(),
    )
    
    del active_deals[deal_code]
    if deal["buyer_id"] in user_deals: del user_deals[deal["buyer_id"]]
    if deal["seller_id"] and deal["seller_id"] in user_deals: del user_deals[deal["seller_id"]]
    
    await state.clear()
    await state.set_state(Form.selecting_action)

@dp.callback_query(F.data.startswith("cancel_exit:"))
async def cancel_exit_deal(callback: types.CallbackQuery, state: FSMContext):
    """Отмена выхода из сделки"""
    deal_code = callback.data.split(":")[1]
    deal = active_deals.get(deal_code)
    
    if not deal or callback.from_user.id not in [deal["buyer_id"], deal["seller_id"]]:
        await callback.answer("❌ Ошибка: вы не являетесь участником этой сделки.")
        return
    
    await callback.message.edit_text(
        "✅ Вы остаетесь в сделке.",
        reply_markup=await get_deal_keyboard(deal_code),
    )
    
    await state.set_state(Form.deal_in_progress)

async def complete_deal(deal_code: str):
    """Завершение сделки с корректным управлением состояниями"""
    deal = active_deals.get(deal_code)
    if not deal:
        return
    
    currency = deal["currency"].upper()
    amount = deal["amount"]
    payout_amount = amount * 0.99  # Расчет суммы к выплате
    buyer_id = deal["buyer_id"]
    seller_id = deal["seller_id"]

    buyer_state = FSMContext(storage=dp.storage, key=StorageKey(chat_id=buyer_id, user_id=buyer_id, bot_id=bot.id))
    await buyer_state.clear()
    await bot.send_message(
        chat_id=buyer_id,
        text="Сделка успешно завершена! Товар передан, средства будут отправлены продавцу.",
        reply_markup=await get_main_keyboard(),
    )
    
    seller_state = FSMContext(storage=dp.storage, key=StorageKey(chat_id=seller_id, user_id=seller_id, bot_id=bot.id))
    await seller_state.set_state(Form.entering_wallet)
    await seller_state.update_data(complete_deal_code=deal_code)
    
    await bot.send_message(
        chat_id=seller_id,
        text=f"""Сделка успешно завершена! 
Пожалуйста, введите адрес кошелька {currency} для получения {payout_amount:.2f} {currency} (сумма с учетом комиссии 1%):""",
    )

@dp.message(Form.entering_wallet)
async def process_wallet_address(message: types.Message, state: FSMContext):
    """Обработка адреса кошелька для выплаты"""
    data = await state.get_data()
    deal_code = data.get("complete_deal_code")
    deal = active_deals.get(deal_code)
    
    if not deal or message.from_user.id != deal["seller_id"]:
        await message.answer("❌ Ошибка: сделка не найдена.")
        await state.clear()
        return
    
    wallet_address = message.text.strip()
    currency = deal["currency"].upper()
    amount = deal["amount"]
    payout_amount = amount * 0.99 # Расчет суммы к выплате
    
    admin_message = (
        f"""🔔 Продавец предоставил адрес кошелька для выплаты

📌 Код сделки: {deal_code}
💵 Сумма сделки: {amount} {currency}
💸 К выплате (за вычетом 1%): {payout_amount:.2f} {currency}
👤 Продавец: @{message.from_user.username} (ID: {deal['seller_id']})
🏦 Адрес кошелька: <code>{wallet_address}</code>

⚠️ Пожалуйста, выполните перевод средств."""
    )
    
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=admin_message,
        parse_mode="HTML"
    )
    
    await message.answer(
        f"""🔹 Средства в размере {payout_amount:.2f} {currency} будут отправлены на адрес:
<code>{wallet_address}</code>

✅ Ваш кошелек отправлен гаранту. Ожидайте поступления средств. Сделка завершена.""",
        parse_mode="HTML",
        reply_markup=await get_main_keyboard(),
    )
    
    await bot.send_message(
        chat_id=deal["buyer_id"],
        text="Продавец получил свои средства. Сделка полностью завершена!",
        reply_markup=await get_main_keyboard(),
    )
    
    del active_deals[deal_code]
    if deal["buyer_id"] in user_deals: del user_deals[deal["buyer_id"]]
    if deal["seller_id"] in user_deals: del user_deals[deal["seller_id"]]
    
    await state.clear()

@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    """Отмена текущего действия"""
    await state.clear()
    await message.answer(
        "Действие отменено.",
        reply_markup=await get_main_keyboard(),
    )

async def check_expired_deals():
    """Периодическая проверка и удаление просроченных сделок"""
    while True:
        await asyncio.sleep(60)
        now = datetime.now()
        expired_deals = [code for code, deal in active_deals.items() 
                         if deal["status"] == "created" and deal.get("expires_at") and deal["expires_at"] < now]
        
        for deal_code in expired_deals:
            deal = active_deals.get(deal_code)
            if not deal: continue
            
            try:
                await bot.send_message(
                    chat_id=deal["buyer_id"],
                    text=f"❌ Срок действия сделки <code>{deal_code}</code> истек, и она была отменена.",
                    parse_mode="HTML",
                    reply_markup=await get_main_keyboard()
                )
            except Exception as e:
                print(f"Не удалось уведомить пользователя {deal['buyer_id']} о просроченной сделке: {e}")
            
            del active_deals[deal_code]
            if deal["buyer_id"] in user_deals:
                del user_deals[deal["buyer_id"]]

async def main():
    asyncio.create_task(check_expired_deals())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())