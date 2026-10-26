"""Temporary object-storage adapters."""

from adapters.outbound.storage.qiniu import QiniuTemporaryFileStore, TemporaryFileStoreError

__all__ = ["QiniuTemporaryFileStore", "TemporaryFileStoreError"]
