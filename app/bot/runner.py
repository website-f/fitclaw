from app.bot.handlers import build_application
from app.core.config import get_settings
from app.core.database import init_db

settings = get_settings()


def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required for the bot service.")

    init_db()
    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()
