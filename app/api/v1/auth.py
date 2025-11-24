from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime

from app.deps import get_db
from app.crud import (
    create_user,
    get_user_by_email,
    log_activity,
    revoke_token
)
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_token
)
from app.schemas import Token, UserCreate, UserRead

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


@router.post("/register", response_model=UserRead)
async def register(u: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await get_user_by_email(db, u.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already exists")

    hashed = get_password_hash(u.password)
    user = await create_user(
        db,
        email=u.email,
        username=u.username,
        hashed_password=hashed
    )

    await log_activity(db, user.id, "register", f"User {user.email} registered")
    return user


@router.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(),
                db: AsyncSession = Depends(get_db)):

    user = await get_user_by_email(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    token = create_access_token(subject=user.email)
    await log_activity(db, user.id, "login", "User logged in")

    return {"access_token": token, "token_type": "bearer"}


@router.post("/logout")
async def logout(token: str = Depends(oauth2_scheme),
                 db: AsyncSession = Depends(get_db)):

    payload = decode_token(token)
    jti = payload.get("jti")
    exp = payload.get("exp")

    expires_at = datetime.utcfromtimestamp(exp)
    await revoke_token(db, jti, expires_at)

    return {"ok": True, "message": "Logged out"}
