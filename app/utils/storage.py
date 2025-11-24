from pathlib import Path
from uuid import uuid4
from fastapi import UploadFile
from app.core.config import settings

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
