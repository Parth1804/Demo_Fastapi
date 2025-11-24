from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.deps import get_current_user, get_db
from app.schemas import ShareReq, UsageResp
from app.utils.storage import save_upload_file
from app.utils.nsfw_check import is_nsfw
from app.crud import (
    create_file,
    share_file,
    log_activity,
    get_user_by_email
)
from app.models import File as FileModel, FileShare, Usage

router = APIRouter()


@router.post("/upload")
async def upload(
    upload_file: UploadFile = File(...),
    current=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    stored_path, size = await save_upload_file(current.id, upload_file)

    # NSFW check
    if is_nsfw(stored_path):
        import os
        os.remove(stored_path)
        await log_activity(db, current.id, "upload_blocked", f"NSFW blocked: {upload_file.filename}")
        raise HTTPException(status_code=400, detail="Uploading NSFW content is not allowed")

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
    record = res.scalar_one_or_none()

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
