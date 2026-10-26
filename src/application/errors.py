"""Errors whose technical details must not leak into presentation surfaces."""


class ApplicationError(RuntimeError):
    """Base error with a stable, human-readable message for UI clients."""

    user_message = "处理过程中发生错误，请稍后重试。"


class UserInputError(ValueError):
    """An input problem whose message is intentionally safe to show to users."""
