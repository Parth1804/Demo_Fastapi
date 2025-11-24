from sqlmodel import select
from app.models import (
    User,
    File,
    FileShare,
    Usage,
    ActivityLog,
    RevokedToken,
)
from sqlmodel.ext.asyncio.session import AsyncSession
from datetime import datetime


# -------------------------
# User helpers
# -------------------------
async def create_user(
    session: AsyncSession, *, email: str, username: str, hashed_password: str, role: str = "user"
) -> User:
    user = User(email=email, username=username, hashed_password=hashed_password, role=role)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    q = select(User).where(User.email == email)
    res = await session.execute(q)
    return res.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


# -------------------------
# File helpers
# -------------------------
async def create_file(
    session: AsyncSession, owner_id: int, filename: str, stored_path: str, content_type: str, size: int
) -> File:
    f = File(owner_id=owner_id, filename=filename, stored_path=stored_path, content_type=content_type, size=size)
    session.add(f)
    await session.commit()
    await session.refresh(f)
    return f


# -------------------------
# Sharing / Usage
# -------------------------
async def share_file(
    session: AsyncSession,
    file_id: int,
    owner_id: int,
    recipient_id: int,
    bytes_transferred: int,
    message: str | None = None,
) -> FileShare:
    s = FileShare(
        file_id=file_id,
        owner_id=owner_id,
        recipient_id=recipient_id,
        bytes_transferred=bytes_transferred,
        message=message,
    )
    session.add(s)

    # update usage summary
    q = select(Usage).where(Usage.owner_id == owner_id, Usage.recipient_id == recipient_id)
    res = await session.execute(q)
    usage = res.scalar_one_or_none()
    if not usage:
        usage = Usage(owner_id=owner_id, recipient_id=recipient_id, total_bytes=bytes_transferred, updated_at=datetime.utcnow())
        session.add(usage)
    else:
        usage.total_bytes += bytes_transferred
        usage.updated_at = datetime.utcnow()
        session.add(usage)

    await session.commit()
    await session.refresh(s)
    return s


# -------------------------
# Activity & token revocation
# -------------------------
async def log_activity(session: AsyncSession, user_id: int, action: str, details: str | None = None):
    a = ActivityLog(user_id=user_id, action=action, details=details)
    session.add(a)
    await session.commit()


async def revoke_token(session: AsyncSession, jti: str, expires_at: datetime):
    rt = RevokedToken(jti=jti, expires_at=expires_at)
    session.add(rt)
    await session.commit()


async def is_token_revoked(session: AsyncSession, jti: str) -> bool:
    q = select(RevokedToken).where(RevokedToken.jti == jti)
    res = await session.execute(q)
    return res.scalar_one_or_none() is not None
