import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from openai import AsyncOpenAI

# Логирование
logging.basicConfig(level=logging.INFO)

# Инициализация (берем из Environment Variables на Render)
TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher()
client = AsyncOpenAI(api_key=OPENAI_KEY)

# Пока используем словарь, позже прикрутим PostgreSQL
user_history = {}

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer("Бот запущен и готов к работе! Привет, Искандер.")

@dp.message()
async def chat_with_gpt(message: types.Message):
    user_id = message.from_user.id
    
    # Инициализация истории
    if user_id not in user_history:
        user_history[user_id] = [{"role": "system", "content": "Ты профессиональный помощник."}]
    
    user_history[user_id].append({"role": "user", "content": message.text})

    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=user_history[user_id]
        )
        answer = response.choices[0].message.content
        user_history[user_id].append({"role": "assistant", "content": answer})
        
        # Ограничение памяти (последние 15 сообщений)
        if len(user_history[user_id]) > 16:
            user_history[user_id] = [user_history[user_id][0]] + user_history[user_id][-15:]
            
        await message.answer(answer)
    except Exception as e:
        logging.error(f"Error: {e}")
        await message.answer("Ошибка связи с ИИ. Проверь ключи.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
