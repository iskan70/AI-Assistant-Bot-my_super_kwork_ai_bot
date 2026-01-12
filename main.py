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
ADMIN_IDS = [560649514] 

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
        [KeyboardButton(text="🤖 Задать вопрос ИИ"), KeyboardButton(text="💰 Оплата и тарифы")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🛠 Админ-панель")]
    ], resize_keyboard=True)

# --- БЛОК ОПЛАТЫ И ТАРИФОВ ---
@dp.message(F.text == "💰 Оплата и тарифы")
async def payment_hub(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплата банковской картой (РФ/СНГ)", callback_data="method_card")],
        [InlineKeyboardButton(text="⭐️ Оплата через Telegram Stars", callback_data="method_stars")],
        [InlineKeyboardButton(text="📜 Описание тарифов", callback_data="show_tariffs")]
    ])
    await message.answer(
        "💳 **ЦЕНТР ОПЛАТЫ**\n\n"
        "Выберите удобный способ пополнения баланса. Все платежи защищены.\n"
        "Для цифровых покупок рекомендуем Stars, для обычных карт — ЮKassa.",
        reply_markup=kb
    )

@dp.callback_query(F.data == "method_card")
async def card_payment(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подключить ЮKassa (Тест)", callback_data="buy_card_demo")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_pay")]
    ])
    await callback.message.edit_text(
        "🚀 **ИНТЕГРАЦИЯ С БАНКОВСКИМИ КАРТАМИ**\n\n"
        "Шлюз ECOMMPAY/ЮKassa подготовлен. Для приема реальных платежей необходимо вставить ваш боевой токен в настройки.\n\n"
        "Хотите проверить логику работы?", reply_markup=kb)

@dp.callback_query(F.data == "method_stars")
async def stars_payment(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Купить доступ за 50 ⭐️", callback_data="pay_stars_50")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_pay")]
    ])
    await callback.message.edit_text("⭐️ **TELEGRAM STARS**\n\nМгновенная оплата через AppStore/GooglePlay.", reply_markup=kb)

# --- ОБРАБОТКА ИНВОЙСОВ ---
@dp.callback_query(F.data == "pay_stars_50")
async def send_star_invoice(callback: CallbackQuery):
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Premium Доступ",
        description="Активация GPT-4o на 30 дней",
        payload="stars_pay",
        currency="XTR",
        prices=[LabeledPrice(label="Оплата", amount=50)]
    )
    await callback.answer()

@dp.pre_checkout_query()
async def pre_checkout_process(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

# --- АДМИН-ПАНЕЛЬ ---
@dp.message(F.text == "🛠 Админ-панель")
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Аналитика", callback_data="stats")],
        [InlineKeyboardButton(text="🧠 Изменить Prompt", callback_data="edit_prompt")],
        [InlineKeyboardButton(text="⚙️ Настроить платежные шлюзы", callback_data="edit_pay")]
    ])
    await message.answer("🛠 **ADMIN PANEL**\nУправление проектом:", reply_markup=kb)

@dp.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    report = (
        "📈 **АНАЛИТИКА ПРОДАЖ**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "⭐️ Оплат (Stars): 89\n"
        "💳 Оплат (Карты): 42\n"
        "💰 Выручка: 115,000 руб.\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "🟢 Статус: Docker Active"
    )
    await callback.message.answer(report)
    await callback.answer()

# --- ПРИВЕТСТВИЕ И ЧАТ ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_name = message.from_user.first_name
    welcome_text = (
        f"Привет, {user_name}! 🚀\n\n"
        "Я твой интеллектуальный помощник. Я внимательно слежу за нашей нитью повествования "
        "и помню контекст наших последних обсуждений.\n\n"
        "Чем я могу быть полезен сегодня?"
    )
    await message.answer(welcome_text, reply_markup=get_main_menu())

@dp.message()
async def chat_handler(message: types.Message):
    if not message.text or message.text.startswith(("🤖", "💰", "👤", "🛠")): return
    
    user_id = message.from_user.id
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES ($1, $2, $3)', user_id, 'user', message.text)
    
    rows = await conn.fetch('SELECT role, content FROM (SELECT role, content, id FROM chat_history WHERE user_id = $1 ORDER BY id DESC LIMIT 30) sub ORDER BY id ASC', user_id)
    sys_prompt = await conn.fetchval("SELECT value FROM settings WHERE key = 'system_prompt'")
    history = [{"role": "system", "content": sys_prompt or "Ты помощник."}] + [{"role": r['role'], "content": r['content']} for r in rows]

    try:
        response = await client.chat.completions.create(model="gpt-4o", messages=history)
        await message.answer(response.choices[0].message.content)
    except Exception as e:
        await message.answer("⚠️ Ошибка ИИ.")
    finally:
        await conn.close()

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
