import base64
import secrets

from app.core.config import get_settings

settings = get_settings()


def is_valid_agent_basic_auth(header_value: str | None) -> bool:
    if not header_value or not header_value.startswith("Basic "):
        return False

    try:
        decoded = base64.b64decode(header_value.split(" ", 1)[1]).decode("utf-8")
        username, password = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return False

    return secrets.compare_digest(username, settings.agent_basic_auth_username) and secrets.compare_digest(
        password, settings.agent_api_shared_key
    )

