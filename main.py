import asyncio
import logging
from telegram.ext import ApplicationBuilder
from config import TELEGRAM_TOKEN
from db import init_db
from handlers import register_handlers
from tasks import setup_scheduler

# ========== LOGGING CONFIG ==========
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("telegram").setLevel(logging.INFO)
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
# ====================================

def main():
    # 1) Инициализация БД (создание таблиц + devices.json)
    asyncio.run(init_db())

    # 2) Создаём Telegram-приложение
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # 3) Регистрируем хэндлеры
    register_handlers(app)

    # 4) Настраиваем JobQueue (встроенный планировщик PTB)
    setup_scheduler(app)

    # 5) Запуск polling (блокирующий, он же стартует цикл и JobQueue)
    app.run_polling()

if __name__ == "__main__":
    main()
