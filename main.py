# main.py

import asyncio
from telegram.ext import ApplicationBuilder
from config import TELEGRAM_TOKEN
from db import init_db
from handlers import register_handlers
from tasks import start_scheduler

async def main():
    # 1) Инициализация БД и устройств
    await init_db()

    # 2) Создание и настройка приложения
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # 3) Регистрация всех обработчиков
    register_handlers(app)

    # 4) Запуск планировщика переходов
    await start_scheduler(app)

    # 5) Запуск polling
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
