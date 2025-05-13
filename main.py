# main.py
import logging
from telegram.ext import ApplicationBuilder
from config import TELEGRAM_TOKEN
from db import init_db
from handlers import register_handlers
from tasks import setup_scheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

# Этот колбэк будет вызван внутри event loop ДО polling
async def on_startup(app):
    await init_db()

def main():
    # 1) Создаём приложение, региструем on_startup
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(on_startup)
        .build()
    )

    # 2) Регистрируем хэндлеры и шедулер
    register_handlers(app)
    setup_scheduler(app)

    # 3) Запускаем polling — PTB сам создаст цикл и вызовет on_startup
    app.run_polling()

if __name__ == "__main__":
    main()
