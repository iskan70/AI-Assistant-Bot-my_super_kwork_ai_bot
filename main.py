import os
import asyncio
import logging
import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO)

# Инициализация из Environment Variables
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(api_key=OPENAI_KEY)

# Функция для работы с БД
async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            role TEXT,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    await conn.close()

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user_name = message.from_user.first_name
    await message.answer(f"Привет, {user_name}! 🚀\nЯ твой AI-помощник с памятью в PostgreSQL. Я помню последние 30 сообщений.")

@dp.message()
async def chat_handler(message: types.Message):
    user_id = message.from_user.id
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    # 1. Сохраняем сообщение юзера
    await conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES ($1, $2, $3)', 
                       user_id, 'user', message.text)
    
    # 2. Получаем последние 30 сообщений для контекста
    rows = await conn.fetch('''
        SELECT role, content FROM (
            SELECT role, content, id FROM chat_history 
            WHERE user_id = $1 
            ORDER BY id DESC LIMIT 30
        ) sub ORDER BY id ASC
    ''', user_id)
    
    history = [{"role": "system", "content": "Ты профессиональный помощник."}]
    for row in rows:
        history.append({"role": row['role'], "content": row['content']})

    try:
        # 3. Запрос к OpenAI
        response = await client.chat.completions.create(model="gpt-4o", messages=history)
        answer = response.choices[0].message.content
        
        # 4. Сохраняем ответ бота
        await conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES ($1, $2, $3)', 
                           user_id, 'assistant', answer)
        
        await message.answer(answer)
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.answer("Ошибка ИИ. Проверь баланс или настройки.")
    finally:
        await conn.close()

async def main():
    await init_db() # Создаем таблицу при запуске
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
