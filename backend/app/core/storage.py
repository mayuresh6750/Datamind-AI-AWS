from datetime import datetime

from supabase import Client

from app.core.config import settings


class StorageClient:
    """Wrapper around Supabase Storage for the four-layer architecture."""

    def __init__(self, supabase: Client | None = None) -> None:
        if supabase is None:
            from app.core.database import get_supabase

            supabase = get_supabase()
        self._sb = supabase

    # ── Layer 1: Raw / Archive ────────────────────────────────────────────────

    def archive_path(self, user_id: str, dataset_id: str, filename: str) -> str:
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
        return f"{user_id}/{dataset_id}/{ts}/{filename}"

    def get_archive_upload_url(self, path: str) -> str:
        response = self._sb.storage.from_(settings.storage_archive_bucket).create_signed_upload_url(path)
        return response["signedUrl"]

    def download_archive(self, path: str) -> bytes:
        return self._sb.storage.from_(settings.storage_archive_bucket).download(path)

    def get_archive_download_url(self, path: str, expires_in: int = 3600) -> str:
        response = self._sb.storage.from_(settings.storage_archive_bucket).create_signed_url(
            path, expires_in
        )
        return response["signedUrl"]

    # ── Layer 2: Curated JSON ─────────────────────────────────────────────────

    def json_path(self, user_id: str, dataset_id: str, version: int = 1) -> str:
        return f"{user_id}/{dataset_id}/v{version}/data.json"

    def upload_json(self, user_id: str, dataset_id: str, data: bytes, version: int = 1) -> str:
        path = self.json_path(user_id, dataset_id, version)
        self._sb.storage.from_(settings.storage_json_bucket).upload(
            path, data, {"content-type": "application/json", "upsert": "true"}
        )
        return path

    def download_json(self, path: str) -> bytes:
        return self._sb.storage.from_(settings.storage_json_bucket).download(path)
