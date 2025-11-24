from fastapi import APIRouter, Depends
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.deps import get_current_user, require_admin, get_db
from app.schemas import UserRead
from app.models import User

router = APIRouter()


@router.get("/me", response_model=UserRead)
async def me(current=Depends(get_current_user)):
    return current


@router.get("/", response_model=list[UserRead], dependencies=[Depends(require_admin)])
async def list_users(db: AsyncSession = Depends(get_db)):
    result = await db.exec(select(User).order_by(User.created_at.desc()))
    return result.all()
