"""Cloudflare R2 storage service wrapping boto3 S3 client."""

from __future__ import annotations

import logging

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

logger = logging.getLogger("insightxpert.storage.r2")


class R2StorageService:
    """Best-effort R2 object storage. All methods are synchronous -- callers
    should use ``asyncio.to_thread()`` to avoid blocking the event loop."""

    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        endpoint_url: str,
        bucket: str,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=BotoConfig(
                signature_version="s3v4",
                retries={"max_attempts": 2, "mode": "standard"},
            ),
        )

    def upload_file(
        self, key: str, content: bytes, content_type: str = "application/octet-stream"
    ) -> bool:
        """Upload bytes to R2. Returns True on success, False on failure."""
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
            )
            return True
        except (ClientError, Exception) as exc:
            logger.error("R2 upload failed for key=%s: %s", key, exc)
            return False

    def delete_file(self, key: str) -> bool:
        """Delete an object from R2. Returns True on success, False on failure."""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
            return True
        except (ClientError, Exception) as exc:
            logger.error("R2 delete failed for key=%s: %s", key, exc)
            return False

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str | None:
        """Generate a presigned GET URL. Returns None on failure."""
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except (ClientError, Exception) as exc:
            logger.error("R2 presigned URL failed for key=%s: %s", key, exc)
            return None
