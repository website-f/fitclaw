import logging
from logging.handlers import RotatingFileHandler
import sys

from ai_ops_agent.paths import ensure_runtime_dirs, log_path


def configure_logging(background: bool = False) -> logging.Logger:
    ensure_runtime_dirs()
    logger = logging.getLogger("ai_ops_agent")
    logger.setLevel(logging.INFO)

    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = RotatingFileHandler(log_path(), maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if not background:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    logger.propagate = False
    return logger

