"""Port for short-lived files that external services need to download."""

from typing import Protocol

from application.dto.documents import InputFile


class TemporaryFileStorePort(Protocol):
    def upload(self, file: InputFile) -> str:
        """Upload a file and return its opaque object key."""

    def create_download_url(self, key: str, expires_in_seconds: int) -> str:
        """Create a time-limited URL for one stored object."""

    def delete(self, key: str) -> None:
        """Delete one stored object."""
