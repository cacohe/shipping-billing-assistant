from __future__ import annotations

from dataclasses import dataclass

import pytest

from adapters.outbound.storage.qiniu import QiniuTemporaryFileStore, TemporaryFileStoreError
from application.dto.documents import InputFile


@dataclass
class FakeResponseInfo:
    status_code: int
    text_body: str = ""


class FakeAuth:
    def __init__(self) -> None:
        self.upload_requests: list[tuple[str, str, int]] = []
        self.download_requests: list[tuple[str, int]] = []

    def upload_token(self, bucket: str, key: str, expires: int) -> str:
        self.upload_requests.append((bucket, key, expires))
        return "upload-token"

    def private_download_url(self, url: str, expires: int) -> str:
        self.download_requests.append((url, expires))
        return f"{url}?e=123&token=signed"


class FakeBucketManager:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.deleted: list[tuple[str, str]] = []

    def delete(self, bucket: str, key: str) -> tuple[None, FakeResponseInfo]:
        self.deleted.append((bucket, key))
        return None, FakeResponseInfo(self.status_code, "delete failed")


def test_upload_sign_and_delete_temporary_file() -> None:
    auth = FakeAuth()
    manager = FakeBucketManager()
    uploaded: list[tuple[str, str, bytes, str, bool]] = []

    def upload(
        token: str,
        key: str,
        data: bytes,
        *,
        mime_type: str,
        check_crc: bool,
    ) -> tuple[dict[str, str], FakeResponseInfo]:
        uploaded.append((token, key, data, mime_type, check_crc))
        return {"key": key, "hash": "hash"}, FakeResponseInfo(200)

    store = QiniuTemporaryFileStore(
        "access-key",
        "secret-key",
        "billing-demo",
        "http://files.example.test",
        auth=auth,
        bucket_manager=manager,
        uploader=upload,
    )

    key = store.upload(InputFile("invoice 1.PDF", b"pdf", "application/pdf"))
    url = store.create_download_url(key, 600)
    store.delete(key)

    assert key.startswith("ocr-inputs/") and key.endswith(".pdf")
    assert uploaded == [("upload-token", key, b"pdf", "application/pdf", True)]
    assert auth.upload_requests == [("billing-demo", key, 600)]
    assert auth.download_requests == [(f"http://files.example.test/{key}", 600)]
    assert url == f"http://files.example.test/{key}?e=123&token=signed"
    assert manager.deleted == [("billing-demo", key)]


def test_upload_rejects_empty_content() -> None:
    store = QiniuTemporaryFileStore(
        "access-key", "secret-key", "billing-demo", "http://files.example.test"
    )

    with pytest.raises(TemporaryFileStoreError, match="没有可上传"):
        store.upload(InputFile("invoice.pdf", b""))


def test_upload_wraps_qiniu_failure_without_exposing_credentials() -> None:
    def failed_upload(*args: object, **kwargs: object) -> tuple[None, FakeResponseInfo]:
        return None, FakeResponseInfo(401, "secret-key authorization failed")

    store = QiniuTemporaryFileStore(
        "access-key",
        "secret-key",
        "billing-demo",
        "http://files.example.test",
        uploader=failed_upload,
    )

    with pytest.raises(TemporaryFileStoreError) as error:
        store.upload(InputFile("invoice.pdf", b"pdf"))

    assert "secret-key" not in str(error.value)


def test_delete_reports_qiniu_failure() -> None:
    store = QiniuTemporaryFileStore(
        "access-key",
        "secret-key",
        "billing-demo",
        "http://files.example.test",
        bucket_manager=FakeBucketManager(status_code=599),
    )

    with pytest.raises(TemporaryFileStoreError, match="删除失败"):
        store.delete("ocr-inputs/file.pdf")
