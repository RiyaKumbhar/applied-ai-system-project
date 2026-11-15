"""Logging setup: console + rotating file (logs/vibematch.log). Never logs API keys."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_configured = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    global _configured
    logger = logging.getLogger("vibematch")
    if _configured:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)
    try:
        LOG_DIR.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(LOG_DIR / "vibematch.log", maxBytes=500_000, backupCount=2)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError:  # read-only filesystem etc.: console logging is enough
        logger.warning("could not open log file; logging to console only")
    logger.propagate = False
    _configured = True
    return logger
