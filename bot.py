import os
import json
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

from dotenv import load_dotenv

from ai import ask_ai

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=TOKEN)
dp = Dispatcher()

USERS_FILE = "users.json"


def load_users() -> set:
    if not os.path.exists(USERS_FILE):
        return set()
    with open(USERS_FILE, "r") as f:
        data = json.load(f)
    return set(data.get("chat_ids", []))


def save_users(users: set):
    with open(USERS_FILE, "w") as f:
        json.dump({"chat_ids": list(users)}, f, indent=2)


AI_USERS = load_users()


# -------- START --------
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 Бот запущено\n"
        "Напишіть запитання"
    )

# -------- AI MODE --------
@dp.message(Command("ai"))
async def ai_mode(message: Message):
    user_id = message.from_user.id

    if user_id != ADMIN_ID and user_id not in AI_USERS:
        await message.answer("Нема доступу")
        return

    AI_USERS.add(user_id)
    save_users(AI_USERS)

    await message.answer("🤖 Режим ШІ увімкнено")

# -------- CHAT --------
@dp.message()
async def chat(message: Message):
    if message.from_user.id not in AI_USERS:
        return

    answer = ask_ai(message.text)
    await message.answer(answer)


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())