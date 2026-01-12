import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    LabeledPrice, PreCheckoutQuery, CallbackQuery, 
    InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
)
from openai import AsyncOpenAI

# 1. КОНФИГУРАЦИЯ
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(api_key=OPENAI_KEY)
logging.basicConfig(level=logging.INFO)

# 2. КЛАВИАТУРЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ (Reply-кнопки внизу)
def get_main_menu():
    buttons = [
        [KeyboardButton(text="🤖 Задать вопрос ИИ"), KeyboardButton(text="💎 Тарифы")],
        [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="⚙️ Настройки")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# 3. ИНИЦИАЛИЗАЦИЯ БАЗЫ
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

# 4. АДМИН-ПАНЕЛЬ (ОТКРЫТА ДЛЯ ВСЕХ В ДЕМО-РЕЖИМЕ)
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    kb = [
        [InlineKeyboardButton(text="📊 Аналитика (Real-time)", callback_data="stats")],
        [InlineKeyboardButton(text="🧠 Настройка личности ИИ", callback_data="edit_prompt")],
        [InlineKeyboardButton(text="📝 Изменить тексты", callback_data="edit_texts")],
        [InlineKeyboardButton(text="💳 Управление платежами", callback_data="test_pay")]
    ]
    await message.answer(
        "🛠 **ADMIN PANEL v1.0 (DEMO ACCESS)**\n\n"
        "Вы получили доступ к панели управления. Здесь заказчик может мониторить бизнес-показатели и менять логику ИИ без программиста.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )

@dp.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    report = (
        "📈 **ОТЧЕТ АНАЛИТИКИ**\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "👤 Всего юзеров: 1,240\n"
        "💬 Запросов к ИИ: 45,890\n"
        "✅ Успешных оплат: 89\n"
        "💰 Выручка: 4,450 ⭐️ (Stars)\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "🌐 Хостинг: Docker Container\n"
        "🐘 БД: PostgreSQL"
    )
    await callback.message.answer(report)
    await callback.answer()

# 5. ГЛАВНОЕ МЕНЮ И СТАРТ
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_name = message.from_user.first_name
    await message.answer(
        f"Привет, {user_name}! 🚀\n\nЯ твой AI-помощник нового поколения.\n"
        "Используй меню ниже для навигации или просто напиши мне вопрос.",
        reply_markup=get_main_menu()
    )

# Обработка кнопок меню
@dp.message(F.text == "💎 Тарифы")
async def pricing(message: types.Message):
    kb = [[InlineKeyboardButton(text="Купить 50 ⭐️", callback_data="test_pay")]]
    await message.answer("Выберите подходящий тариф для безлимитного доступа к GPT-4o:", 
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.message(F.text == "👤 Мой профиль")
async def profile(message: types.Message):
    await message.answer(f"👤 **Профиль:** {message.from_user.first_name}\n🔑 **Статус:** Демо-доступ\n✉️ **Лимит сообщений:** 10/100")

# 6. ОПЛАТА
@dp.callback_query(F.data == "test_pay")
async def send_invoice(callback: CallbackQuery):
    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Premium AI Access",
        description="Подписка на 30 дней",
        payload="month_sub",
        currency="XTR", 
        prices=[LabeledPrice(label="Активировать", amount=50)]
    )
    await callback.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

# 7. ЧАТ С ПАМЯТЬЮ
@dp.message()
async def chat_handler(message: types.Message):
    if not message.text or message.text.startswith("🤖"): return
    
    user_id = message.from_user.id
    conn = await asyncpg.connect(DATABASE_URL)
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
        await message.answer("⚠️ Ошибка ИИ.")
    finally:
        await conn.close()

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
