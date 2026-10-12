"""Byte transfer through presigned S3 URLs, independent of what the bytes are.

QA evidence and shared files both move bytes with a plain HTTPS PUT or GET
against a URL a project credential or the hosted signer minted. Failures
carry a stable code and the ``s3://bucket/key`` they addressed.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Optional

TRANSFER_TIMEOUT_S = 60


class ObjectTransferError(RuntimeError):
    """A presigned PUT or GET did not complete."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def put_signed_object(
    upload_url: str,
    *,
    bucket: str,
    key: str,
    content: bytes,
    content_type: Optional[str],
) -> None:
    """PUT ``content`` to a presigned URL, refusing every non-2xx answer."""
    request = urllib.request.Request(
        upload_url,
        data=content,
        method="PUT",
        headers={"Content-Type": content_type or "application/octet-stream"},
    )
    address = f"s3://{bucket}/{key}"
    try:
        with urllib.request.urlopen(request, timeout=TRANSFER_TIMEOUT_S) as response:
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raise ObjectTransferError(
            "s3_upload_failed",
            f"S3 upload failed for {address}: HTTP {exc.code} {exc.reason}",
        ) from exc
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise ObjectTransferError(
            "s3_upload_failed", f"S3 upload failed for {address}: {exc}"
        ) from exc
    if not 200 <= status < 300:
        raise ObjectTransferError(
            "s3_upload_failed", f"S3 upload failed for {address}: HTTP {status}"
        )


def get_signed_object(
    download_url: str,
    *,
    bucket: str,
    key: str,
    max_bytes: int,
) -> bytes:
    """GET one object through a presigned URL, bounded by ``max_bytes``.

    A 404, or the 403 S3 answers for a missing key when the signer may not
    list the bucket, is ``s3_object_missing``; other failures are
    ``s3_download_failed``.
    """
    address = f"s3://{bucket}/{key}"
    try:
        with urllib.request.urlopen(
            download_url, timeout=TRANSFER_TIMEOUT_S
        ) as response:
            content = response.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404):
            raise ObjectTransferError(
                "s3_object_missing",
                f"no readable object at {address} (S3 answered HTTP {exc.code})",
            ) from exc
        raise ObjectTransferError(
            "s3_download_failed",
            f"S3 download failed for {address}: HTTP {exc.code} {exc.reason}",
        ) from exc
    except (OSError, urllib.error.URLError, ValueError) as exc:
        raise ObjectTransferError(
            "s3_download_failed", f"S3 download failed for {address}: {exc}"
        ) from exc
    if len(content) > max_bytes:
        raise ObjectTransferError(
            "s3_object_too_large",
            f"object {address} exceeds the {max_bytes}-byte read limit",
        )
    return content


__all__ = [
    "ObjectTransferError",
    "TRANSFER_TIMEOUT_S",
    "get_signed_object",
    "put_signed_object",
]
