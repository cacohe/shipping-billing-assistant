import logging

from bootstrap.logging_config import APP_LOGGER_NAME, configure_logging


def test_configure_logging_is_idempotent() -> None:
    logger = configure_logging("DEBUG")
    handler_count = len(logger.handlers)

    configured_again = configure_logging("INFO")

    assert configured_again is logger
    assert len(logger.handlers) == handler_count
    assert logger.level == logging.INFO


def test_configure_logging_falls_back_for_invalid_level() -> None:
    logger = configure_logging("not-a-level")

    assert logger.name == APP_LOGGER_NAME
    assert logger.level == logging.INFO
