from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.deps import get_current_user, get_db
from app.schemas import ShareReq, UsageResp
from app.utils.storage import save_upload_file
from app.crud import (
    create_file,
    share_file,
    log_activity,
    get_user_by_email
)
from app.models import File as FileModel, FileShare, Usage

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
    # Save the file first
    stored_path, size = await save_upload_file(current.id, upload_file)

    # Only run NSFW detection for images and videos.
    # For videos, you should implement frame sampling in nsfw_check (optional).
    content_type = (upload_file.content_type or "").lower()

    # Image-only NSFW check (video optional)
    if _is_image_content_type(content_type) or _is_video_content_type(content_type):
        # lazy import to avoid overhead when not used
        from app.utils.nsfw_check import predict_image, is_nsfw

        try:
            # For images: is_nsfw returns bool
            # For videos: your nsfw util should sample frames and return True if any frame flagged
            blocked = is_nsfw(stored_path)
        except Exception as exc:
            # If the detector fails for an image/video, decide policy:
            # Conservative: block -> safer but might block legitimate files.
            # Permissive: allow -> safer UX but risk letting content through.
            # We choose permissive for unexpected detector errors *for now* so text uploads aren't blocked,
            # but still log the event so admins can review.
            await log_activity(db, current.id, "nsfw_check_error", f"Detector error: {exc}")
            blocked = False

        if blocked:
            # remove file if you want to avoid storing blocked content
            import os
            try:
                os.remove(stored_path)
            except Exception:
                pass
            await log_activity(db, current.id, "upload_blocked", f"NSFW blocked: {upload_file.filename}")
            raise HTTPException(status_code=400, detail="Uploading NSFW content is not allowed")

    # For non-image/video content, we skip NSFW check
    f = await create_file(
        db,
        owner_id=current.id,
        filename=upload_file.filename,
        stored_path=stored_path,
        content_type=upload_file.content_type,
        size=size
    )

    await log_activity(db, current.id, "upload", f"Uploaded file {f.filename}")

    return {
        "id": f.id,
        "filename": f.filename,
        "size": f.size
    }


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

    # Compatibility-safe extraction:
    # - If result supports scalar_one_or_none(), use it
    # - Otherwise fall back to scalars().first()
    try:
        # preferred (if available)
        record = res.scalar_one_or_none()
    except AttributeError:
        # fallback for environments where scalar_one_or_none isn't present
        try:
            record = res.scalars().first()
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
        return FileResponse(file_obj.stored_path, filename=file_obj.filename)

    # shared recipient can download
    q = await db.exec(
        select(FileShare)
        .where(FileShare.file_id == file_id, FileShare.recipient_id == current.id)
    )
    if q.scalar_one_or_none():
        return FileResponse(file_obj.stored_path, filename=file_obj.filename)

    # admin can download
    if current.role == "admin":
        return FileResponse(file_obj.stored_path, filename=file_obj.filename)

    raise HTTPException(status_code=403, detail="Forbidden")
