# main.py

import asyncio
import logging
from telegram.ext import ApplicationBuilder
from config import TELEGRAM_TOKEN
from db import init_db
from handlers import register_handlers
from tasks import setup_scheduler

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

async def main():
    # 1) Инициализация БД
    await init_db()

    # 2) Создаём приложение и регистрируем хэндлеры
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    register_handlers(app)
    setup_scheduler(app)

    # 3) Запуск polling внутри этого же цикла
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
