"""
Object Storage Client for DataMind AI.

100% Native Amazon S3 enterprise cloud storage engine.
Uses boto3 and AWS S3 Pre-Signed URLs for high-durability, zero-server-I/O file operations.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog

from app.core.s3 import get_s3_service

log = structlog.get_logger()


class StorageClient:
    """
    Native Amazon S3 Object Storage Client.
    Manages raw dataset archives, curated JSON versions, and pre-signed S3 URLs.
    """

    def __init__(self, s3_service=None) -> None:
        self._s3 = s3_service or get_s3_service()

    # ── Layer 1: Raw / Archive ────────────────────────────────────────────────

    def archive_path(self, user_id: str, dataset_id: str, filename: str) -> str:
        """Constructs an S3 object key prefix for raw archive datasets."""
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        return f"{user_id}/{dataset_id}/{ts}/{filename}"

    def get_archive_upload_url(self, path: str) -> str:
        """
        Generates a direct pre-signed PUT URL to Amazon S3.
        The client browser uploads directly to S3 without hitting backend memory.
        """
        return self._s3.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._s3.bucket, "Key": f"archive/{path}"},
            ExpiresIn=3600,
        )

    def download_archive(self, path: str) -> bytes:
        """Downloads the raw archive dataset bytes directly from Amazon S3."""
        response = self._s3.client.get_object(
            Bucket=self._s3.bucket,
            Key=f"archive/{path}",
        )
        return response["Body"].read()

    def get_archive_download_url(self, path: str, expires_in: int = 3600) -> str:
        """Generates a secure, temporary pre-signed GET URL for downloading from Amazon S3."""
        return self._s3.generate_presigned_url(f"archive/{path}", expires_in=expires_in)

    # ── Layer 2: Curated JSON ─────────────────────────────────────────────────

    def json_path(self, user_id: str, dataset_id: str, version: int = 1) -> str:
        """Constructs S3 object key for cleaned, curated JSON dataset versions."""
        return f"{user_id}/{dataset_id}/v{version}/data.json"

    def upload_json(self, user_id: str, dataset_id: str, data: bytes, version: int = 1) -> str:
        """Uploads curated JSON dataset to Amazon S3."""
        path = self.json_path(user_id, dataset_id, version)
        self._s3.client.put_object(
            Bucket=self._s3.bucket,
            Key=f"curated/{path}",
            Body=data,
            ContentType="application/json",
        )
        return path

    def download_json(self, path: str) -> bytes:
        """Retrieves curated JSON dataset bytes from Amazon S3."""
        response = self._s3.client.get_object(
            Bucket=self._s3.bucket,
            Key=f"curated/{path}",
        )
        return response["Body"].read()

    def summary_path(self, user_id: str, dataset_id: str) -> str:
        """Constructs S3 object key for dataset statistical summary metadata."""
        return f"{user_id}/{dataset_id}/_summary.json"

    def upload_summary(self, user_id: str, dataset_id: str, data: bytes) -> str:
        """Stores dataset summary JSON in Amazon S3."""
        path = self.summary_path(user_id, dataset_id)
        self._s3.client.put_object(
            Bucket=self._s3.bucket,
            Key=f"curated/{path}",
            Body=data,
            ContentType="application/json",
        )
        return path
