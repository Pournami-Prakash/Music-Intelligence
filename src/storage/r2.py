"""
Cloudflare R2 storage helpers (S3-compatible via boto3).

Free tier limits enforced:
  - Storage: 10 GB/month  (we warn at 9 GB, block at 9.5 GB)
  - Class A ops: 1M/month (writes)
  - Class B ops: 10M/month (reads)
  - Egress: free

Usage:
    from src.storage.r2 import R2Client
    r2 = R2Client()
    r2.upload("data/processed/playlists.parquet", "processed/playlists.parquet")
    r2.download("processed/playlists.parquet", "data/processed/playlists.parquet")
"""

import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(Path(__file__).parent.parent.parent / ".env")

WARN_BYTES  = 9.0 * 1024 ** 3   # 9 GB
BLOCK_BYTES = 9.5 * 1024 ** 3   # 9.5 GB
FREE_LIMIT  = 10.0 * 1024 ** 3  # 10 GB


class R2Client:
    def __init__(self):
        account_id = os.getenv("R2_ACCOUNT_ID")
        self.bucket = os.getenv("R2_BUCKET", "music-intelligence-atlas")

        if not account_id:
            raise EnvironmentError("R2_ACCOUNT_ID not set in .env")

        self.s3 = boto3.client(
            "s3",
            endpoint_url=os.getenv("R2_ENDPOINT", f"https://{account_id}.r2.cloudflarestorage.com"),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )

    # ── Size guard ────────────────────────────────────────────────────────────

    def bucket_size_bytes(self) -> int:
        """Return total bytes currently stored in the bucket."""
        total = 0
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket):
            for obj in page.get("Contents", []):
                total += obj["Size"]
        return total

    def _existing_object_size(self, r2_key: str) -> int:
        """Return size of an existing object, 0 if it doesn't exist."""
        try:
            resp = self.s3.head_object(Bucket=self.bucket, Key=r2_key)
            return resp["ContentLength"]
        except ClientError:
            return 0

    def _check_space(self, upload_bytes: int, r2_key: str = "") -> None:
        current     = self.bucket_size_bytes()
        existing    = self._existing_object_size(r2_key) if r2_key else 0
        after       = current - existing + upload_bytes  # subtract old size on overwrite
        current_gb  = current / 1024**3
        after_gb    = after   / 1024**3

        if after > BLOCK_BYTES:
            raise RuntimeError(
                f"Upload blocked: would bring bucket to {after_gb:.2f} GB "
                f"(limit: {FREE_LIMIT/1024**3:.0f} GB free tier). "
                f"Current usage: {current_gb:.2f} GB."
            )
        if after > WARN_BYTES:
            print(f"  [warning] Bucket will reach {after_gb:.2f} GB after upload "
                  f"— approaching 10 GB free limit.", file=sys.stderr)

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload(self, local_path: str | Path, r2_key: str, delete_after: bool = False) -> None:
        local_path = Path(local_path)
        if not local_path.exists():
            raise FileNotFoundError(f"{local_path} not found")

        file_bytes = local_path.stat().st_size
        self._check_space(file_bytes, r2_key)

        print(f"  → uploading {local_path.name} ({file_bytes/1024**3:.2f} GB) to R2:{r2_key}")

        # multipart for files > 100 MB
        if file_bytes > 100 * 1024 * 1024:
            self._multipart_upload(local_path, r2_key, file_bytes)
        else:
            self.s3.upload_file(str(local_path), self.bucket, r2_key)

        print(f"     done → s3://{self.bucket}/{r2_key}")

        if delete_after:
            local_path.unlink()
            print(f"     deleted local copy: {local_path}")

    def _multipart_upload(self, local_path: Path, r2_key: str, file_bytes: int) -> None:
        part_size = 64 * 1024 * 1024  # 64 MB parts
        mpu = self.s3.create_multipart_upload(Bucket=self.bucket, Key=r2_key)
        upload_id = mpu["UploadId"]
        parts = []

        try:
            with open(local_path, "rb") as f:
                part_num = 1
                with tqdm(total=file_bytes, unit="B", unit_scale=True, desc=local_path.name) as pbar:
                    while chunk := f.read(part_size):
                        resp = self.s3.upload_part(
                            Bucket=self.bucket,
                            Key=r2_key,
                            UploadId=upload_id,
                            PartNumber=part_num,
                            Body=chunk,
                        )
                        parts.append({"PartNumber": part_num, "ETag": resp["ETag"]})
                        pbar.update(len(chunk))
                        part_num += 1

            self.s3.complete_multipart_upload(
                Bucket=self.bucket,
                Key=r2_key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except Exception:
            self.s3.abort_multipart_upload(Bucket=self.bucket, Key=r2_key, UploadId=upload_id)
            raise

    # ── Download ──────────────────────────────────────────────────────────────

    def download(self, r2_key: str, local_path: str | Path) -> None:
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        if local_path.exists():
            print(f"  [skip] {local_path.name} already exists locally")
            return

        print(f"  → downloading R2:{r2_key} → {local_path}")
        self.s3.download_file(self.bucket, r2_key, str(local_path))
        print(f"     done")

    # ── List / exists ─────────────────────────────────────────────────────────

    def list_keys(self, prefix: str = "") -> list[str]:
        keys = []
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def exists(self, r2_key: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket, Key=r2_key)
            return True
        except ClientError:
            return False

    def usage_summary(self) -> None:
        total = self.bucket_size_bytes()
        keys  = self.list_keys()
        print(f"\nR2 bucket: {self.bucket}")
        print(f"  Objects : {len(keys)}")
        print(f"  Used    : {total/1024**3:.2f} GB / 10.00 GB free tier")
        print(f"  Free    : {(FREE_LIMIT - total)/1024**3:.2f} GB remaining\n")


if __name__ == "__main__":
    r2 = R2Client()
    r2.usage_summary()
