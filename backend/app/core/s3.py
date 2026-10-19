"""
Amazon S3 Storage Service Layer.

Provides:
- S3Service: Thread-safe, non-blocking upload/download for raw datasets and JSON artifacts.
- Pre-signed URL generation for offloading direct client downloads to AWS S3.
- Idempotent bucket creation and lifecycle management.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import structlog

from app.core.config import settings

log = structlog.get_logger()


class S3Service:
    """
    Amazon S3 Object Storage Service for DataMind AI.
    Handles raw dataset archives (CSV/Excel) and processed dashboard JSON artifacts.
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
    ) -> None:
        self.bucket = bucket_name or settings.aws_s3_bucket
        self.region = region or settings.aws_region
        self._access_key = access_key_id or settings.aws_access_key_id
        self._secret_key = secret_access_key or settings.aws_secret_access_key

        session_kwargs = {
            "region_name": self.region,
            "config": Config(signature_version="s3v4"),
        }
        if self._access_key and self._secret_key:
            session_kwargs["aws_access_key_id"] = self._access_key
            session_kwargs["aws_secret_access_key"] = self._secret_key

        self.client = boto3.client("s3", **session_kwargs)

    def configure_cors(self) -> bool:
        """
        Configures S3 bucket CORS to permit browser pre-signed PUT/GET direct uploads.
        """
        cors_configuration = {
            "CORSRules": [
                {
                    "AllowedHeaders": ["*"],
                    "AllowedMethods": ["GET", "PUT", "POST", "HEAD", "DELETE"],
                    "AllowedOrigins": ["*"],
                    "ExposeHeaders": ["ETag", "x-amz-request-id", "x-amz-id-2"],
                    "MaxAgeSeconds": 3000,
                }
            ]
        }
        try:
            self.client.put_bucket_cors(Bucket=self.bucket, CORSConfiguration=cors_configuration)
            log.info("s3_cors_configured", bucket=self.bucket)
            return True
        except Exception as exc:
            log.warning("s3_cors_config_failed", bucket=self.bucket, error=str(exc))
            return False

    def ensure_bucket_exists(self) -> bool:
        """
        Idempotently verifies if the configured S3 bucket exists, or creates it.
        Handles AWS us-east-1 constraint rules and configures CORS.
        """
        try:
            self.client.head_bucket(Bucket=self.bucket)
            log.info("s3_bucket_verified", bucket=self.bucket, region=self.region)
            self.configure_cors()
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchBucket"):
                log.info("s3_bucket_creating", bucket=self.bucket, region=self.region)
                try:
                    if self.region == "us-east-1":
                        # us-east-1 does not accept LocationConstraint in CreateBucketConfiguration
                        self.client.create_bucket(Bucket=self.bucket)
                    else:
                        self.client.create_bucket(
                            Bucket=self.bucket,
                            CreateBucketConfiguration={"LocationConstraint": self.region},
                        )
                    log.info("s3_bucket_created_successfully", bucket=self.bucket)
                    return True
                except Exception as create_exc:
                    log.error("s3_bucket_creation_failed", bucket=self.bucket, error=str(create_exc))
                    return False
            log.warning("s3_head_bucket_warning", bucket=self.bucket, error=str(exc))
            return False

    async def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Uploads in-memory bytes to S3 non-blockingly via asyncio threadpool executor.
        Returns the s3:// URI.
        """
        loop = asyncio.get_running_loop()

        def _sync_upload():
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )

        await loop.run_in_executor(None, _sync_upload)
        s3_uri = f"s3://{self.bucket}/{key}"
        log.info("s3_upload_success", key=key, size_bytes=len(data), s3_uri=s3_uri)
        return s3_uri

    async def download_bytes(self, key: str) -> bytes:
        """
        Downloads object bytes from S3 non-blockingly.
        """
        loop = asyncio.get_running_loop()

        def _sync_download() -> bytes:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()

        data = await loop.run_in_executor(None, _sync_download)
        log.info("s3_download_success", key=key, size_bytes=len(data))
        return data

    def generate_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Generates a secure, temporary pre-signed S3 download URL.
        Directs client traffic to AWS S3 CDN rather than our FastAPI backend.
        """
        url = self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        log.info("s3_presigned_url_generated", key=key, expires_in_sec=expires_in)
        return url

    async def delete_object(self, key: str) -> bool:
        """
        Deletes an object from S3.
        """
        loop = asyncio.get_running_loop()

        def _sync_delete():
            self.client.delete_object(Bucket=self.bucket, Key=key)

        try:
            await loop.run_in_executor(None, _sync_delete)
            log.info("s3_delete_success", key=key)
            return True
        except Exception as exc:
            log.warning("s3_delete_failed", key=key, error=str(exc))
            return False


_s3_instance: Optional[S3Service] = None


def get_s3_service() -> S3Service:
    """Returns the singleton S3Service instance."""
    global _s3_instance
    if _s3_instance is None:
        _s3_instance = S3Service()
    return _s3_instance
