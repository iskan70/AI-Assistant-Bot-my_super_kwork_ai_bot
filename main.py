import os, asyncio, logging, asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, PreCheckoutQuery
from openai import AsyncOpenAI

# 1. КОНФИГУРАЦИЯ
ADMIN_ID = 494255577  # <-- ОБЯЗАТЕЛЬНО ЗАМЕНИ НА СВОЙ ID (узнай в @userinfobot)
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(api_key=OPENAI_KEY)
logging.basicConfig(level=logging.INFO)

# 2. ИНИЦИАЛИЗАЦИЯ БД
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY, user_id BIGINT, role TEXT, content TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT);
        INSERT INTO settings (key, value) VALUES ('system_prompt', 'Ты профессиональный помощник.') ON CONFLICT DO NOTHING;
    ''')
    await conn.close()

# 3. АДМИН-ПАНЕЛЬ И АНАЛИТИКА
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    kb = [
        [types.InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [types.InlineKeyboardButton(text="🧠 Сменить личность ИИ", callback_data="edit_prompt")],
        [types.InlineKeyboardButton(text="⭐️ Тест оплаты (Stars)", callback_data="test_pay")]
    ]
    await message.answer("👑 АДМИН-ПАНЕЛЬ\nУправляйте ботом и смотрите аналитику:", 
                         reply_markup=types.InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.Callback_query):
    conn = await asyncpg.connect(DATABASE_URL)
    users = await conn.fetchval('SELECT COUNT(DISTINCT user_id) FROM chat_history')
    msgs = await conn.fetchval('SELECT COUNT(*) FROM chat_history')
    today = await conn.fetchval("SELECT COUNT(DISTINCT user_id) FROM chat_history WHERE created_at > NOW() - INTERVAL '1 day'")
    await callback.message.answer(f"📈 АНАЛИТИКА:\n\n👤 Всего юзеров: {users}\n💬 Всего сообщений: {msgs}\n🔥 Активны за 24ч: {today}")
    await conn.close()

# 4. МОНЕТИЗАЦИЯ (TELEGRAM STARS)
@dp.callback_query(F.data == "test_pay")
async def send_invoice(callback: types.Callback_query):
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Подписка на AI",
        description="Доступ к GPT-4o на 1 месяц",
        payload="month_sub",
        currency="XTR",  # XTR = Telegram Stars
        prices=[LabeledPrice(label="Купить", amount=50)] # 50 звезд
    )

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def success_payment(message: types.Message):
    await message.answer("✅ Оплата прошла успешно! Спасибо за поддержку.")

# 5. ОСНОВНОЙ ЧАТ И ПАМЯТЬ
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_name = message.from_user.first_name
    await message.answer(f"Привет, {user_name}! 🚀\nЯ твой мощный AI-помощник. Я помню контекст нашей беседы. Чем помочь?")

@dp.message()
async def chat_handler(message: types.Message):
    user_id = message.from_user.id
    conn = await asyncpg.connect(DATABASE_URL)
    
    # Сохраняем и получаем историю (30 сообщений)
    await conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES ($1, $2, $3)', user_id, 'user', message.text)
    rows = await conn.fetch('SELECT role, content FROM (SELECT role, content, id FROM chat_history WHERE user_id = $1 ORDER BY id DESC LIMIT 30) sub ORDER BY id ASC', user_id)
    
    # Получаем System Prompt из базы
    sys_prompt = await conn.fetchval("SELECT value FROM settings WHERE key = 'system_prompt'")
    history = [{"role": "system", "content": sys_prompt}] + [{"role": r['role'], "content": r['content']} for r in rows]

    try:
        response = await client.chat.completions.create(model="gpt-4o", messages=history)
        answer = response.choices[0].message.content
        await conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES ($1, $2, $3)', user_id, 'assistant', answer)
        await message.answer(answer)
    except Exception as e:
        await message.answer("⚠️ Ошибка ИИ. Проверьте API ключ.")
    finally:
        await conn.close()

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
