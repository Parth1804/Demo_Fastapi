import os
import tempfile
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.deps import get_current_user, get_db
from app.schemas import ShareReq, UsageResp
from app.utils.storage import save_upload_file, upload_file_to_cloudinary
from app.crud import (
    create_file,
    share_file,
    log_activity,
    get_user_by_email
)
from app.models import File as FileModel, FileShare, Usage
from app.core.config import settings

router = APIRouter()


def _is_image_content_type(content_type: str | None) -> bool:
    return bool(content_type and content_type.startswith("image/"))


def _is_video_content_type(content_type: str | None) -> bool:
    return bool(content_type and content_type.startswith("video/"))


@router.post("/upload")
async def upload(
    upload_file: UploadFile = File(...),
    current=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload flow:
    1. Read bytes once and write to a temp file.
    2. If image/video -> run NSFW check on temp file.
    3. If NSFW -> block and delete temp file.
    4. Upload temp file to Cloudinary (if configured) -> get secure_url, size
       If Cloudinary not configured or upload fails -> fallback to local save using save_upload_file.
    5. Create DB File record with stored_path set to secure_url (or local path) and size.
    """

    # prepare
    filename = upload_file.filename or "upload"
    content_type = (upload_file.content_type or "").lower()

    # read bytes (consume the UploadFile stream once)
    file_bytes = await upload_file.read()
    file_size_local = len(file_bytes)

    if file_size_local > settings.max_upload_size_bytes:
        raise HTTPException(status_code=400, detail="File too large")

    # write to temp file (so nsfw detector and cloud uploader work with a filesystem path)
    suffix = ""
    if filename:
        _, ext = os.path.splitext(filename)
        suffix = ext or ""

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    try:
        tmp.write(file_bytes)
        tmp.flush()
        tmp.close()

        # Also save a permanent local copy under uploads/<user_id>/ so we always
        # keep a local file even when Cloudinary upload succeeds.
        from pathlib import Path
        owner_dir = Path(settings.upload_dir) / str(current.id)
        owner_dir.mkdir(parents=True, exist_ok=True)
        from uuid import uuid4
        unique_name = f"{uuid4().hex}{suffix}"
        dest_path = owner_dir / unique_name
        with open(dest_path, "wb") as f:
            f.write(file_bytes)
        local_path = str(dest_path)

        # NSFW check for images and videos (use your existing nsfw utils)
        if _is_image_content_type(content_type) or _is_video_content_type(content_type):
            try:
                # import here to avoid heavy imports globally
                from app.utils.nsfw_check import predict_image, is_nsfw
                blocked = False
                # call is_nsfw on the local file path.
                try:
                    blocked = is_nsfw(local_path)
                except Exception:
                    # If detector fails, log error and proceed permissively
                    await log_activity(db, current.id, "nsfw_check_error", "Detector runtime error during upload")
                    blocked = False

                if blocked:
                    await log_activity(db, current.id, "upload_blocked", f"NSFW blocked: {filename}")
                    raise HTTPException(status_code=400, detail="Uploading NSFW content is not allowed")
            except HTTPException:
                # re-raise NSFW blocking
                raise
            except Exception as exc:
                # If nsfw_check import or call fails, log and move on (permissive)
                await log_activity(db, current.id, "nsfw_check_error", f"NSFW init error: {exc}")

        # Try Cloudinary upload (uses the local permanent copy `local_path`)
        stored_cloud_url = None
        size = file_size_local
        cloud_attempted = False

        if settings.cloudinary_api_key and settings.cloudinary_api_secret and settings.cloudinary_cloud_name:
            try:
                cloud_attempted = True
                folder = f"{settings.cloudinary_upload_folder.rstrip('/')}/{current.id}"
                # use resource_type='raw' for non-image/video files so Cloudinary accepts them
                res = await upload_file_to_cloudinary(
                    local_path,
                    public_id=None,
                    folder=folder,
                    resource_type=("image" if _is_image_content_type(content_type) or _is_video_content_type(content_type) else "raw"),
                )
                stored_cloud_url = res.get("secure_url") or res.get("url")
                size = int(res.get("bytes") or file_size_local or 0)
            except Exception as exc:
                await log_activity(db, current.id, "cloudinary_error", f"{exc}")
                stored_cloud_url = None

        # create DB record with BOTH local stored path and optional cloud URL
        f = await create_file(
            db,
            owner_id=current.id,
            filename=filename,
            stored_path=local_path,
            cloud_url=stored_cloud_url,
            content_type=content_type if content_type else None,
            size=size,
        )

        await log_activity(db, current.id, "upload", f"Uploaded file {f.filename} (cloud={'yes' if cloud_attempted and stored_cloud_url else 'no'})")

        return {
            "id": f.id,
            "filename": f.filename,
            "size": f.size,
            "stored_path": f.stored_path,
            "cloud_url": getattr(f, "cloud_url", None),
        }

    finally:
        # ensure temp file cleanup
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@router.post("/share")
async def share(
    req: ShareReq,
    current=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    recipient = await get_user_by_email(db, req.recipient_email)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found")

    file_obj = await db.get(FileModel, req.file_id)
    if not file_obj or file_obj.owner_id != current.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    share_entry = await share_file(
        db,
        file_id=file_obj.id,
        owner_id=current.id,
        recipient_id=recipient.id,
        bytes_transferred=file_obj.size,
        message=req.message
    )

    from app.core.email import send_local_email
    send_local_email(
        recipient.email,
        f"File shared by {current.email}",
        f"{current.username} shared '{file_obj.filename}' with you"
    )

    await log_activity(
        db,
        current.id,
        "share",
        f"Shared file {file_obj.filename} to {recipient.email}"
    )

    return {"ok": True, "share_id": share_entry.id}


@router.get("/usage/{owner_id}/{recipient_id}", response_model=UsageResp)
async def get_usage(
    owner_id: int,       
    recipient_id: int,
    current=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # only owner OR admin allowed
    if current.id != owner_id and current.role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    q = select(Usage).where(Usage.owner_id == owner_id, Usage.recipient_id == recipient_id)
    res = await db.exec(q)

    # Compatibility-safe extraction across SQLAlchemy/SQLModel versions.
    record = None
    if hasattr(res, "scalar_one_or_none"):
        try:
            record = res.scalar_one_or_none()
        except Exception:
            record = None
    if record is None and hasattr(res, "one_or_none"):
        try:
            record = res.one_or_none()
        except Exception:
            record = None
    if record is None and hasattr(res, "scalars"):
        try:
            record = res.scalars().first()
        except Exception:
            record = None
    if record is None and hasattr(res, "first"):
        try:
            record = res.first()
        except Exception:
            record = None

    if not record:
        raise HTTPException(status_code=404, detail="No usage record")

    return record


@router.get("/download/{file_id}")
async def download(
    file_id: int,
    current=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    file_obj = await db.get(FileModel, file_id)
    if not file_obj:
        raise HTTPException(status_code=404, detail="File not found")

    # owner can download
    if file_obj.owner_id == current.id:
        # If stored_path looks like a URL (cloud), redirect or return URL
        if str(file_obj.stored_path).startswith("http"):
            # for cloud assets, return the URL
            return {"url": file_obj.stored_path}
        return FileResponse(file_obj.stored_path, filename=file_obj.filename)

    # shared recipient can download
    q = await db.exec(
        select(FileShare)
        .where(FileShare.file_id == file_id, FileShare.recipient_id == current.id)
    )
    if q.scalar_one_or_none():
        if str(file_obj.stored_path).startswith("http"):
            return {"url": file_obj.stored_path}
        return FileResponse(file_obj.stored_path, filename=file_obj.filename)

    # admin can download
    if current.role == "admin":
        if str(file_obj.stored_path).startswith("http"):
            return {"url": file_obj.stored_path}
        return FileResponse(file_obj.stored_path, filename=file_obj.filename)

    raise HTTPException(status_code=403, detail="Forbidden")
