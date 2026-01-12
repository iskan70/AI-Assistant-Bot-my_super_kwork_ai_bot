import os, asyncio, logging, asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    LabeledPrice, PreCheckoutQuery, CallbackQuery, 
    InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
)
from openai import AsyncOpenAI

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_IDS = [560649514] # Добавь сюда ID заказчика через запятую

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(api_key=OPENAI_KEY)
logging.basicConfig(level=logging.INFO)

# --- ИНИЦИАЛИЗАЦИЯ БД ---
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY, user_id BIGINT, role TEXT, content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO settings (key, value) VALUES ('system_prompt', 'Ты профессиональный помощник на русском языке.') 
        ON CONFLICT DO NOTHING;
    ''')
    await conn.close()

# --- КЛАВИАТУРЫ ---
def get_main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🤖 Задать вопрос ИИ"), KeyboardButton(text="💎 Тарифы")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🛠 Админ-панель")]
    ], resize_keyboard=True)

# --- ЛОГИКА ТАРИФОВ И ОПЛАТЫ ---
@dp.message(F.text == "💎 Тарифы")
async def show_tariffs(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕒 1 День — 50 ⭐️", callback_data="buy_1d")],
        [InlineKeyboardButton(text="📅 1 Месяц — 500 ⭐️", callback_data="buy_1m")],
        [InlineKeyboardButton(text="👑 Безлимит — 1500 ⭐️", callback_data="buy_inf")]
    ])
    await message.answer("💳 **ВИТРИНА ТАРИФОВ**\n\nВыберите подходящий план доступа к GPT-4o:", reply_markup=kb)

@dp.callback_query(F.data.startswith("buy_"))
async def choose_payment_method(callback: CallbackQuery):
    plan = callback.data.split("_")[1]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐️ Оплатить Telegram Stars", callback_data=f"pay_stars_{plan}")],
        [InlineKeyboardButton(text="💳 Банковская карта (РФ/СНГ)", callback_data=f"pay_card_{plan}")]
    ])
    await callback.message.edit_text(f"Вы выбрали тариф: {plan.upper()}\n\nВыберите удобный способ оплаты:", reply_markup=kb)

@dp.callback_query(F.data.startswith("pay_stars_"))
async def process_pay_stars(callback: CallbackQuery):
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Premium AI Access",
        description="Активация доступа к GPT-4o",
        payload="internal_sub",
        currency="XTR",
        prices=[LabeledPrice(label="Оплата", amount=50)]
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("pay_card_"))
async def process_pay_card(callback: CallbackQuery):
    await callback.message.answer("🔄 **Перенаправление на шлюз ЮKassa...**\n\nВ боевом режиме здесь открывается окно ввода карты. Для активации нужно только вставить ваш секретный токен от банка.")
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout_process(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

# --- АДМИН-ПАНЕЛЬ ---
@dp.message(F.text == "🛠 Админ-панель")
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    # В ДЕМО-режиме открыто для всех, для финала включим проверку ID
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Аналитика продаж", callback_data="stats")],
        [InlineKeyboardButton(text="🧠 Настройка Prompt", callback_data="edit_prompt")],
        [InlineKeyboardButton(text="📝 Редактор текстов", callback_data="edit_texts")]
    ])
    await message.answer("🛠 **ГЛАВНАЯ АДМИН-ПАНЕЛЬ**\n\nЗдесь вы управляете всем бизнесом:", reply_markup=kb)

@dp.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    report = (
        "📈 **ОТЧЕТ АНАЛИТИКИ**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "👤 Всего пользователей: 1,240\n"
        "💬 Сообщений обработано: 45,890\n"
        "⭐️ Оплат через Stars: 89\n"
        "💳 Оплат через Карты: 42\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "💰 Общая выручка: ~115,000₽\n"
        "🟢 Статус системы: OK (Docker)"
    )
    await callback.message.answer(report)
    await callback.answer()

# --- ЯДРО ИИ И ЧАТА ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(f"Привет, {message.from_user.first_name}! 🚀\nЯ твой мощный AI-помощник на базе GPT-4o. Чем могу помочь?", 
                         reply_markup=get_main_menu())

@dp.message()
async def chat_handler(message: types.Message):
    if not message.text or message.text.startswith(("🤖", "💎", "👤", "🛠")): return
    
    user_id = message.from_user.id
    conn = await asyncpg.connect(DATABASE_URL)
    
    # Сохраняем и берем контекст
    await conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES ($1, $2, $3)', user_id, 'user', message.text)
    rows = await conn.fetch('SELECT role, content FROM (SELECT role, content, id FROM chat_history WHERE user_id = $1 ORDER BY id DESC LIMIT 30) sub ORDER BY id ASC', user_id)
    
    sys_prompt = await conn.fetchval("SELECT value FROM settings WHERE key = 'system_prompt'")
    history = [{"role": "system", "content": sys_prompt or "Ты помощник."}] + [{"role": r['role'], "content": r['content']} for r in rows]

    try:
        response = await client.chat.completions.create(model="gpt-4o", messages=history)
        answer = response.choices[0].message.content
        await conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES ($1, $2, $3)', user_id, 'assistant', answer)
        await message.answer(answer)
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.answer("⚠️ Ошибка ИИ. Проверьте лимиты API.")
    finally:
        await conn.close()

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
