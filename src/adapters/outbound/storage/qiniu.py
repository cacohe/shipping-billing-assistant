"""Qiniu Kodo adapter for short-lived OCR inputs."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote
from uuid import uuid4

from qiniu import Auth, BucketManager, put_data

from application.dto.documents import InputFile
from application.errors import ApplicationError

logger = logging.getLogger("shipping_billing_assistant.storage.qiniu")


class TemporaryFileStoreError(ApplicationError):
    """Raised when a temporary object cannot be stored, signed, or deleted."""

    user_message = "文件临时存储服务暂时不可用，请稍后重试。"


class _ResponseInfo(Protocol):
    status_code: int
    text_body: str


class _Auth(Protocol):
    def upload_token(self, bucket: str, key: str, expires: int) -> str: ...

    def private_download_url(self, url: str, expires: int) -> str: ...


class _BucketManager(Protocol):
    def delete(self, bucket: str, key: str) -> tuple[object, _ResponseInfo]: ...


_Uploader = Callable[..., tuple[Mapping[str, Any] | None, _ResponseInfo]]


class QiniuTemporaryFileStore:
    def __init__(
        self,
        access_key: str,
        secret_key: str,
        bucket: str,
        download_domain: str,
        *,
        auth: _Auth | None = None,
        bucket_manager: _BucketManager | None = None,
        uploader: _Uploader | None = None,
    ) -> None:
        runtime_auth = auth or Auth(access_key, secret_key)
        self._auth = runtime_auth
        self._bucket_manager = bucket_manager or BucketManager(runtime_auth)
        self._uploader = uploader or put_data
        self._bucket = bucket
        self._download_domain = download_domain.rstrip("/")

    def upload(self, file: InputFile) -> str:
        if not file.content:
            logger.warning("拒绝上传空文件 file=%s", file.name)
            raise TemporaryFileStoreError(f"{file.name} 没有可上传的文件内容")
        suffix = Path(file.name).suffix.lower()
        key = f"ocr-inputs/{uuid4().hex}{suffix}"
        logger.info(
            "七牛临时文件上传开始 file=%s size_bytes=%d bucket=%s object_key=%s",
            file.name,
            len(file.content),
            self._bucket,
            key,
        )
        try:
            token = self._auth.upload_token(self._bucket, key, expires=600)
            result, response_info = self._uploader(
                token,
                key,
                file.content,
                mime_type=file.media_type or "application/octet-stream",
                check_crc=True,
            )
        except Exception as exc:
            logger.error("七牛临时文件上传异常 error_type=%s", type(exc).__name__)
            raise TemporaryFileStoreError("七牛临时文件上传失败") from exc
        if response_info.status_code != 200 or result is None or result.get("key") != key:
            logger.error("七牛临时文件上传失败 status=%d", response_info.status_code)
            raise TemporaryFileStoreError(
                f"七牛临时文件上传失败，状态码 {response_info.status_code}"
            )
        logger.info("七牛临时文件上传完成 object_key=%s", key)
        return key

    def create_download_url(self, key: str, expires_in_seconds: int) -> str:
        object_url = f"{self._download_domain}/{quote(key, safe='/')}"
        try:
            signed_url = self._auth.private_download_url(object_url, expires=expires_in_seconds)
        except Exception as exc:
            logger.error("七牛签名下载地址生成异常 error_type=%s", type(exc).__name__)
            raise TemporaryFileStoreError("七牛签名下载地址生成失败") from exc
        if not signed_url.startswith(("http://", "https://")):
            raise TemporaryFileStoreError("七牛未返回有效的签名下载地址")
        logger.debug("七牛签名下载地址生成完成 object_key=%s", key)
        return signed_url

    def delete(self, key: str) -> None:
        try:
            _, response_info = self._bucket_manager.delete(self._bucket, key)
        except Exception as exc:
            logger.error("七牛临时文件删除异常 error_type=%s", type(exc).__name__)
            raise TemporaryFileStoreError("七牛临时文件删除失败") from exc
        if response_info.status_code != 200:
            logger.error("七牛临时文件删除失败 status=%d", response_info.status_code)
            raise TemporaryFileStoreError(
                f"七牛临时文件删除失败，状态码 {response_info.status_code}"
            )
        logger.info("七牛临时文件已删除 object_key=%s", key)
