from __future__ import annotations

import logging

from app.core.app_config import LOG_FILE


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8")],
        force=True,
    )
