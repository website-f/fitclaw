import httpx

from app.core.config import get_settings

settings = get_settings()


class TelegramService:
    @staticmethod
    def send_message(chat_id: str, text: str) -> bool:
        if not settings.telegram_bot_token:
            return False

        response = httpx.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        return bool(payload.get("ok"))

