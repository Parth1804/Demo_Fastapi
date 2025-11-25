from pathlib import Path
from uuid import uuid4
from fastapi import UploadFile
from app.core.config import settings
import os
import tempfile
import asyncio
from concurrent.futures import ThreadPoolExecutor

# keep existing local upload behavior
UPLOAD_DIR = Path(settings.upload_dir)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


async def save_upload_file(owner_id: int, upload_file: UploadFile) -> tuple[str, int]:
    """
    Save uploaded file in user-specific folder.
    Returns: (full file path, file size)
    """
    owner_dir = UPLOAD_DIR / str(owner_id)
    owner_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(upload_file.filename).suffix
    unique_name = f"{uuid4().hex}{suffix}"
    dest_path = owner_dir / unique_name

    file_bytes = await upload_file.read()
    file_size = len(file_bytes)

    if file_size > settings.max_upload_size_bytes:
        raise ValueError("File too large")

    with open(dest_path, "wb") as f:
        f.write(file_bytes)

    return str(dest_path), file_size


try:
    import cloudinary
    import cloudinary.uploader
    _CLOUDINARY_AVAILABLE = True
except Exception:
    _CLOUDINARY_AVAILABLE = False

_executor = ThreadPoolExecutor(max_workers=6)


def _configure_cloudinary():
    if not _CLOUDINARY_AVAILABLE:
        return False
    if not settings.cloudinary_api_key or not settings.cloudinary_api_secret or not settings.cloudinary_cloud_name:
        return False
    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )
    return True


async def upload_file_to_cloudinary(file_path: str, public_id: str | None = None, folder: str | None = None, resource_type: str | None = None):
    """
    Uploads a local file path to Cloudinary and returns the upload response dict.
    Runs the blocking cloudinary.uploader.upload in a threadpool.
    """
    if not _configure_cloudinary():
        raise RuntimeError("Cloudinary not configured or package not installed")

    folder = folder or settings.cloudinary_upload_folder

    def _sync_upload():
        opts = {"folder": folder} if folder else {}
        if public_id:
            opts["public_id"] = public_id
            opts["overwrite"] = True
        # allow caller to override resource_type (e.g., 'raw' for non-image files)
        if resource_type:
            opts["resource_type"] = resource_type
        # let Cloudinary auto-detect resource_type when not provided
        return cloudinary.uploader.upload(file_path, **opts)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_executor, _sync_upload)
    return result


async def upload_uploadfile_obj(upload_file: UploadFile, public_id: str | None = None, folder: str | None = None, resource_type: str | None = None):
    """
    Upload from a FastAPI UploadFile instance (in-memory stream).
    Writes to a temp file then calls upload_file_to_cloudinary.
    Returns the Cloudinary upload result dict.
    """
    # create temp file with same suffix
    suffix = ""
    if upload_file.filename:
        _, ext = os.path.splitext(upload_file.filename)
        suffix = ext or ""

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await upload_file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        res = await upload_file_to_cloudinary(tmp_path, public_id=public_id, folder=folder, resource_type=resource_type)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
    return res


async def delete_from_cloudinary(public_id: str):
    """Delete an asset by public_id. Returns cloudinary response dict."""
    if not _configure_cloudinary():
        raise RuntimeError("Cloudinary not configured or package not installed")

    def _sync_destroy():
        return cloudinary.uploader.destroy(public_id)

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _sync_destroy)
