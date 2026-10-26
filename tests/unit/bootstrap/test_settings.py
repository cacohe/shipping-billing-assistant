from pathlib import Path

import pytest

from bootstrap.settings import Settings


@pytest.fixture(autouse=True)
def isolate_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "LITELLM_MODEL",
        "LITELLM_API_KEY",
        "LITELLM_API_BASE",
        "LITELLM_TIMEOUT_SECONDS",
        "OCR_ENDPOINT",
        "QINIU_ACCESS_KEY",
        "QINIU_SECRET_KEY",
        "QINIU_BUCKET",
        "QINIU_DOMAIN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OCR_ENDPOINT", "https://ocr.example.test/process")


def test_settings_require_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LITELLM_MODEL", raising=False)
    with pytest.raises(ValueError):
        Settings.from_env()


def test_settings_require_ocr_endpoint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LITELLM_MODEL", "openai/test")
    monkeypatch.delenv("OCR_ENDPOINT", raising=False)

    with pytest.raises(ValueError, match="OCR_ENDPOINT"):
        Settings.from_env()


def test_settings_load_dotenv_without_overriding_existing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LITELLM_MODEL=deepseek/deepseek-flash",
                "LITELLM_API_KEY=from-file",
                'LITELLM_API_BASE="https://api.deepseek.com"',
                "QINIU_ACCESS_KEY=access-key",
                "QINIU_SECRET_KEY=secret-key",
                "QINIU_BUCKET=billing-demo",
                "QINIU_DOMAIN=http://files.example.test",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LITELLM_MODEL", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    monkeypatch.delenv("QINIU_ACCESS_KEY", raising=False)
    monkeypatch.delenv("QINIU_SECRET_KEY", raising=False)
    monkeypatch.delenv("QINIU_BUCKET", raising=False)
    monkeypatch.delenv("QINIU_DOMAIN", raising=False)
    monkeypatch.setenv("LITELLM_API_BASE", "https://explicit.test")

    settings = Settings.from_env()

    assert settings.llm_model == "deepseek/deepseek-flash"
    assert settings.log_level == "INFO"
    assert settings.llm_api_key == "from-file"
    assert settings.llm_api_base == "https://explicit.test"
    assert settings.llm_timeout_seconds == 120.0
    assert settings.qiniu_access_key == "access-key"
    assert settings.qiniu_secret_key == "secret-key"
    assert settings.qiniu_bucket == "billing-demo"
    assert settings.qiniu_domain == "http://files.example.test"
    assert settings.temporary_url_ttl_seconds == 600


def test_settings_load_litellm_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LITELLM_MODEL", "openai/test")
    monkeypatch.setenv("LITELLM_API_BASE", "https://llm.test")
    monkeypatch.setenv("LITELLM_TIMEOUT_SECONDS", "45.5")
    settings = Settings.from_env()
    assert settings.llm_model == "openai/test"
    assert settings.llm_api_base == "https://llm.test"
    assert settings.llm_timeout_seconds == 45.5


@pytest.mark.parametrize("value", ["0", "nan", "inf", "-inf"])
def test_settings_reject_invalid_litellm_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LITELLM_MODEL", "openai/test")
    monkeypatch.setenv("LITELLM_TIMEOUT_SECONDS", value)

    with pytest.raises(ValueError, match="LITELLM_TIMEOUT_SECONDS"):
        Settings.from_env()


def test_settings_reject_partial_qiniu_configuration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LITELLM_MODEL", "openai/test")
    monkeypatch.setenv("QINIU_ACCESS_KEY", "access-key")
    monkeypatch.delenv("QINIU_SECRET_KEY", raising=False)
    monkeypatch.delenv("QINIU_BUCKET", raising=False)
    monkeypatch.delenv("QINIU_DOMAIN", raising=False)

    with pytest.raises(ValueError, match="必须同时设置"):
        Settings.from_env()


def test_settings_reject_qiniu_console_url(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LITELLM_MODEL", "openai/test")
    monkeypatch.setenv("QINIU_ACCESS_KEY", "access-key")
    monkeypatch.setenv("QINIU_SECRET_KEY", "secret-key")
    monkeypatch.setenv("QINIU_BUCKET", "billing-demo")
    monkeypatch.setenv("QINIU_DOMAIN", "https://portal.qiniu.com/kodo/bucket")

    with pytest.raises(ValueError, match="下载域名"):
        Settings.from_env()


@pytest.mark.parametrize(
    "domain",
    [
        "https://portal.qiniu.com./kodo/bucket",
        "https://user:password@files.example.test",
        "https://files.example.test/path",
        "https://files.example.test?download=1",
        "https://files.example.test#fragment",
        "http://:80",
    ],
)
def test_settings_reject_non_origin_qiniu_domain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, domain: str
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LITELLM_MODEL", "openai/test")
    monkeypatch.setenv("QINIU_ACCESS_KEY", "access-key")
    monkeypatch.setenv("QINIU_SECRET_KEY", "secret-key")
    monkeypatch.setenv("QINIU_BUCKET", "billing-demo")
    monkeypatch.setenv("QINIU_DOMAIN", domain)

    with pytest.raises(ValueError, match="下载域名"):
        Settings.from_env()
