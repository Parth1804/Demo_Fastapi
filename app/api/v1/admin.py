from fastapi import APIRouter, Depends
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from app.deps import require_admin, get_db
from app.models import ActivityLog, FileShare

router = APIRouter()


@router.get("/activity")
async def activity_log(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin)
):
    q = select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)
    result = await db.exec(q)
    return result.all()


@router.get("/shares")
async def shares(
    db: AsyncSession = Depends(get_db),
    admin=Depends(require_admin)
):
    q = select(FileShare).order_by(FileShare.shared_at.desc()).limit(200)
    result = await db.exec(q)
    return result.all()
