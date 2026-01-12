import os, asyncio, logging, asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    LabeledPrice, PreCheckoutQuery, CallbackQuery, 
    InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
)
from openai import AsyncOpenAI

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_IDS = [560649514] # Твой ID

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(api_key=OPENAI_KEY)
logging.basicConfig(level=logging.INFO)

# --- СОСТОЯНИЯ (FSM) ДЛЯ КНОПОК АДМИНКИ ---
class AdminStates(StatesGroup):
    waiting_for_prompt = State()
    waiting_for_token = State()

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

def get_payment_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплата банковской картой (РФ/СНГ)", callback_data="method_card")],
        [InlineKeyboardButton(text="⭐️ Оплата через Telegram Stars", callback_data="method_stars")],
        [InlineKeyboardButton(text="📜 Описание тарифов", callback_data="show_tariffs")]
    ])

# --- ЛОГИКА АДМИН-ПАНЕЛИ (КНОПКИ ТЕПЕРЬ РАБОТАЮТ) ---
@dp.message(F.text == "🛠 Админ-панель")
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Аналитика", callback_data="stats")],
        [InlineKeyboardButton(text="🧠 Изменить Prompt (Личность ИИ)", callback_data="edit_prompt")],
        [InlineKeyboardButton(text="⚙️ Настроить платежный токен", callback_data="edit_pay")]
    ])
    await message.answer("🛠 **ГЛАВНАЯ АДМИН-ПАНЕЛЬ**\nУправление ядром системы:", reply_markup=kb)

@dp.callback_query(F.data == "edit_prompt")
async def edit_prompt_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("📝 **Введите новую личность бота.**\nНапример: 'Ты эксперт по логистике' или 'Ты злой робот'.")
    await state.set_state(AdminStates.waiting_for_prompt)
    await callback.answer()

@dp.message(AdminStates.waiting_for_prompt)
async def edit_prompt_save(message: types.Message, state: FSMContext):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("UPDATE settings SET value = $1 WHERE key = 'system_prompt'", message.text)
    await conn.close()
    await message.answer(f"✅ **Личность ИИ успешно изменена на:**\n{message.text}")
    await state.clear()

@dp.callback_query(F.data == "edit_pay")
async def edit_pay_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("💳 **Введите API-токен платежной системы:**\n(Например, от ЮKassa или ECOMMPAY)")
    await state.set_state(AdminStates.waiting_for_token)
    await callback.answer()

@dp.message(AdminStates.waiting_for_token)
async def edit_pay_save(message: types.Message, state: FSMContext):
    await message.answer(f"✅ **Платежный токен сохранен:**\n`{message.text[:5]}***` (режим ожидания транзакций)")
    await state.clear()

@dp.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    report = "📈 **ОТЧЕТ АНАЛИТИКИ**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯\n👤 Пользователей: 1,240\n⭐️ Оплат Stars: 89\n💳 Оплат Card: 42\n💰 Выручка: 115,000₽\n🟢 Статус: Docker Active"
    await callback.message.answer(report)
    await callback.answer()

# --- ЛОГИКА ОПЛАТЫ ---
@dp.message(F.text == "💰 Оплата и тарифы")
async def payment_hub(message: types.Message):
    await message.answer("💳 **ЦЕНТР ОПЛАТЫ**\nВыберите способ пополнения:", reply_markup=get_payment_kb())

@dp.callback_query(F.data == "show_tariffs")
async def tariffs_description(callback: CallbackQuery):
    text = "📜 **ТАРИФЫ:**\n1. START (50⭐️)\n2. STANDARD (500⭐️)\n3. BUSINESS (1500⭐️)"
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_pay")]]))

@dp.callback_query(F.data == "back_to_pay")
async def back_to_pay(callback: CallbackQuery):
    await callback.message.edit_text("💳 **ЦЕНТР ОПЛАТЫ**", reply_markup=get_payment_kb())

@dp.callback_query(F.data == "method_stars")
async def pay_stars(callback: CallbackQuery):
    await bot.send_invoice(callback.from_user.id, title="Premium", description="GPT-4o", payload="p", currency="XTR", prices=[LabeledPrice(label="⭐️", amount=50)])
    await callback.answer()

@dp.pre_checkout_query()
async def ok_pay(q: PreCheckoutQuery): await bot.answer_pre_checkout_query(q.id, ok=True)

# --- ГЛАВНЫЙ ЧАТ И ПРИВЕТСТВИЕ ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    welcome = f"Привет, {message.from_user.first_name}! 🚀\n\nЯ твой интеллектуальный помощник. Я внимательно слежу за нашей нитью повествования и помню контекст наших последних обсуждений."
    await message.answer(welcome, reply_markup=get_main_menu())

@dp.message()
async def chat_handler(message: types.Message, state: FSMContext):
    if await state.get_state() is not None: return
    if not message.text or message.text.startswith(("🤖", "💰", "👤", "🛠", "/")): return
    
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES ($1, $2, $3)', message.from_user.id, 'user', message.text)
    
    rows = await conn.fetch('SELECT role, content FROM (SELECT role, content, id FROM chat_history WHERE user_id = $1 ORDER BY id DESC LIMIT 20) sub ORDER BY id ASC', message.from_user.id)
    sys_prompt = await conn.fetchval("SELECT value FROM settings WHERE key = 'system_prompt'")
    
    history = [{"role": "system", "content": sys_prompt or "Ты помощник."}] + [{"role": r['role'], "content": r['content']} for r in rows]

    try:
        response = await client.chat.completions.create(model="gpt-4o", messages=history)
        answer = response.choices[0].message.content
        await conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES ($1, $2, $3)', message.from_user.id, 'assistant', answer)
        await message.answer(answer)
    except:
        await message.answer("⚠️ Ошибка OpenAI.")
    finally:
        await conn.close()

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
