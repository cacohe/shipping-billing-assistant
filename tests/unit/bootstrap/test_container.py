from typing import Any

import pytest

from bootstrap import container
from bootstrap.settings import Settings


def test_build_application_passes_configured_timeout_to_litellm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_model(**options: object) -> object:
        captured.update(options)
        return object()

    monkeypatch.setattr(container, "ChatLiteLLM", fake_model)
    settings = Settings(
        log_level="INFO",
        llm_model="openai/test",
        llm_api_key=None,
        llm_api_base=None,
        llm_timeout_seconds=45.0,
        ocr_endpoint="https://ocr.test",
        qiniu_access_key=None,
        qiniu_secret_key=None,
        qiniu_bucket=None,
        qiniu_domain=None,
        temporary_url_ttl_seconds=600,
    )

    container.build_application(settings)

    assert captured["request_timeout"] == 45.0
