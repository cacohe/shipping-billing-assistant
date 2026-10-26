"""Small, dependency-free logging setup for the demo application."""

import logging
import os

APP_LOGGER_NAME = "shipping_billing_assistant"
_HANDLER_NAME = "shipping-billing-assistant-console"
_DEFAULT_LEVEL = "INFO"
_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def configure_logging(level: str | None = None) -> logging.Logger:
    """Configure an idempotent console logger and return the application logger."""

    configured_level = level or os.getenv("LOG_LEVEL") or _DEFAULT_LEVEL
    requested_level = configured_level.strip().upper()
    effective_level = requested_level if requested_level in _VALID_LEVELS else _DEFAULT_LEVEL

    logger = logging.getLogger(APP_LOGGER_NAME)
    logger.setLevel(effective_level)
    logger.propagate = False

    if not any(handler.get_name() == _HANDLER_NAME for handler in logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.set_name(_HANDLER_NAME)
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(console_handler)

    for existing_handler in logger.handlers:
        if existing_handler.get_name() == _HANDLER_NAME:
            existing_handler.setLevel(effective_level)

    if requested_level not in _VALID_LEVELS:
        logger.warning("无效的 LOG_LEVEL=%s，已回退为 %s", requested_level, _DEFAULT_LEVEL)
    return logger
