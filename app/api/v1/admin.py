from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, delete

from app.deps import require_admin, get_db
from app.models import ActivityLog, FileShare, User, File
from app.schemas import UserRead, UserCreate, AdminUserCreate
from app.crud import create_user
from app.core.security import get_password_hash

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


# --- Admin user management (CRUD) ---


@router.get("/users", response_model=List[UserRead])
async def list_users(db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    q = select(User).order_by(User.created_at.desc()).limit(200)
    res = await db.exec(q)
    return res.all()


@router.get("/users/{user_id}", response_model=UserRead)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/users", response_model=UserRead)
async def admin_create_user(u: AdminUserCreate, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    # create_user helper expects hashed password
    hashed = get_password_hash(u.password)
    # If admin provided a role, allow it; otherwise default to 'user'
    role = getattr(u, "role", None) or "user"
    user = await create_user(db, email=u.email, username=u.username, hashed_password=hashed, role=role)
    return user


@router.put("/users/{user_id}", response_model=UserRead)
async def admin_update_user(user_id: int, payload: UserCreate, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    # Using UserCreate for simplicity: fields email, username, password
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # update allowed fields
    user.email = payload.email
    user.username = payload.username
    if payload.password:
        user.hashed_password = get_password_hash(payload.password)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/users/{user_id}")
async def admin_delete_user(user_id: int, db: AsyncSession = Depends(get_db), admin=Depends(require_admin)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.exec(delete(ActivityLog).where(ActivityLog.user_id == user_id))
    await db.exec(delete(FileShare).where((FileShare.owner_id == user_id) | (FileShare.recipient_id == user_id)))
    await db.exec(delete(File).where(File.owner_id == user_id))
    await db.delete(user)
    await db.commit()
    return {"ok": True}
