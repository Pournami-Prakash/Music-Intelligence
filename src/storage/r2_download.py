"""
Boto3-free R2 object download for the serving runtime.

boto3/botocore add ~40-80 MB of resident memory just to import + build an S3
client — too much for a 512 MB box. The API only ever needs to GET objects, so
this does a minimal AWS SigV4-signed GET with `requests` instead. Same
`download(key, local_path)` signature as R2Client.download, so cache.py's call
sites are unchanged. Uploads/listing still live in src/storage/r2.py (boto3),
used only by local compute jobs (requirements.txt), never imported by the API.
"""
import hashlib
import hmac
import os
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

_ACCOUNT = os.getenv("R2_ACCOUNT_ID", "")
_BUCKET  = os.getenv("R2_BUCKET", "music-intelligence-atlas")
_AK      = os.getenv("R2_ACCESS_KEY_ID", "")
_SK      = os.getenv("R2_SECRET_ACCESS_KEY", "")
_HOST    = os.getenv("R2_ENDPOINT", f"https://{_ACCOUNT}.r2.cloudflarestorage.com").replace("https://", "").replace("http://", "").rstrip("/")
_REGION  = "auto"
_SERVICE = "s3"
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

_session = requests.Session()


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def download(r2_key: str, local_path) -> None:
    """GET s3://{bucket}/{r2_key} to local_path via a SigV4-signed request."""
    local_path = Path(local_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)

    canonical_uri = "/" + urllib.parse.quote(f"{_BUCKET}/{r2_key}", safe="/~")
    now      = datetime.now(timezone.utc)
    amzdate  = now.strftime("%Y%m%dT%H%M%SZ")
    datestp  = now.strftime("%Y%m%d")

    canonical_headers = f"host:{_HOST}\nx-amz-content-sha256:{_EMPTY_SHA256}\nx-amz-date:{amzdate}\n"
    signed_headers    = "host;x-amz-content-sha256;x-amz-date"
    canonical_request = f"GET\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{_EMPTY_SHA256}"

    scope  = f"{datestp}/{_REGION}/{_SERVICE}/aws4_request"
    to_sign = (f"AWS4-HMAC-SHA256\n{amzdate}\n{scope}\n"
               f"{hashlib.sha256(canonical_request.encode()).hexdigest()}")

    k_date    = _hmac(("AWS4" + _SK).encode(), datestp)
    k_region  = _hmac(k_date, _REGION)
    k_service = _hmac(k_region, _SERVICE)
    k_signing = _hmac(k_service, "aws4_request")
    signature = hmac.new(k_signing, to_sign.encode(), hashlib.sha256).hexdigest()

    headers = {
        "Host": _HOST,
        "x-amz-date": amzdate,
        "x-amz-content-sha256": _EMPTY_SHA256,
        "Authorization": (f"AWS4-HMAC-SHA256 Credential={_AK}/{scope}, "
                          f"SignedHeaders={signed_headers}, Signature={signature}"),
    }
    url = f"https://{_HOST}{canonical_uri}"

    tmp = local_path.with_suffix(local_path.suffix + ".part")
    with _session.get(url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                if chunk:
                    f.write(chunk)
    tmp.replace(local_path)
