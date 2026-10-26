"""Environment-based runtime settings."""

import os
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    log_level: str
    llm_model: str
    llm_api_key: str | None
    llm_api_base: str | None
    llm_timeout_seconds: float
    ocr_endpoint: str
    qiniu_access_key: str | None
    qiniu_secret_key: str | None
    qiniu_bucket: str | None
    qiniu_domain: str | None
    temporary_url_ttl_seconds: int

    @property
    def temporary_storage_configured(self) -> bool:
        return all(
            (
                self.qiniu_access_key,
                self.qiniu_secret_key,
                self.qiniu_bucket,
                self.qiniu_domain,
            )
        )

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
        model = os.getenv("LITELLM_MODEL", "").strip()
        if not model:
            raise ValueError("必须设置 LITELLM_MODEL，例如 openai/gpt-4o-mini")
        ocr_endpoint = os.getenv("OCR_ENDPOINT", "").strip()
        if not ocr_endpoint:
            raise ValueError("必须设置 OCR_ENDPOINT，例如 https://ocr.example.com/process")
        parsed_ocr_endpoint = urlparse(ocr_endpoint)
        if parsed_ocr_endpoint.scheme not in {"http", "https"} or not parsed_ocr_endpoint.netloc:
            raise ValueError("OCR_ENDPOINT 必须是有效的 HTTP(S) 地址")
        try:
            llm_timeout = float(os.getenv("LITELLM_TIMEOUT_SECONDS", "120"))
        except ValueError as exc:
            raise ValueError("LITELLM_TIMEOUT_SECONDS 必须是数字") from exc
        if not isfinite(llm_timeout) or llm_timeout <= 0:
            raise ValueError("LITELLM_TIMEOUT_SECONDS 必须大于 0")
        qiniu_config = {
            "access_key": os.getenv("QINIU_ACCESS_KEY", "").strip() or None,
            "secret_key": os.getenv("QINIU_SECRET_KEY", "").strip() or None,
            "bucket": os.getenv("QINIU_BUCKET", "").strip() or None,
            "domain": os.getenv("QINIU_DOMAIN", "").strip() or None,
        }
        configured_values = sum(value is not None for value in qiniu_config.values())
        if configured_values not in (0, len(qiniu_config)):
            raise ValueError(
                "QINIU_ACCESS_KEY、QINIU_SECRET_KEY、QINIU_BUCKET 和 QINIU_DOMAIN 必须同时设置"
            )
        qiniu_domain = qiniu_config["domain"]
        if qiniu_domain:
            parsed_domain = urlparse(qiniu_domain)
            is_origin_only = (
                parsed_domain.path in {"", "/"}
                and not parsed_domain.params
                and not parsed_domain.query
                and not parsed_domain.fragment
                and parsed_domain.username is None
                and parsed_domain.password is None
            )
            if (
                parsed_domain.scheme not in {"http", "https"}
                or not parsed_domain.netloc
                or not parsed_domain.hostname
                or not is_origin_only
            ):
                raise ValueError("QINIU_DOMAIN 必须是包含 http:// 或 https:// 的下载域名")
            hostname = (parsed_domain.hostname or "").rstrip(".").casefold()
            if hostname == "portal.qiniu.com":
                raise ValueError("QINIU_DOMAIN 必须填写 Bucket 下载域名，不能填写七牛控制台地址")
        try:
            url_ttl = int(os.getenv("TEMPORARY_URL_TTL_SECONDS", "600"))
        except ValueError as exc:
            raise ValueError("TEMPORARY_URL_TTL_SECONDS 必须是整数") from exc
        if url_ttl <= 0:
            raise ValueError("TEMPORARY_URL_TTL_SECONDS 必须大于 0")
        return cls(
            log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO",
            llm_model=model,
            llm_api_key=os.getenv("LITELLM_API_KEY") or None,
            llm_api_base=os.getenv("LITELLM_API_BASE") or None,
            llm_timeout_seconds=llm_timeout,
            ocr_endpoint=ocr_endpoint,
            qiniu_access_key=qiniu_config["access_key"],
            qiniu_secret_key=qiniu_config["secret_key"],
            qiniu_bucket=qiniu_config["bucket"],
            qiniu_domain=qiniu_domain,
            temporary_url_ttl_seconds=url_ttl,
        )
