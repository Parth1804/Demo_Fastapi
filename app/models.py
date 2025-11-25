from typing import Optional
from sqlmodel import SQLModel, Field
from datetime import datetime


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    username: str
    hashed_password: str
    role: str = Field(default="user")  # 'user' or 'admin'
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class File(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(foreign_key="user.id")
    filename: str
    stored_path: str
    cloud_url: Optional[str] = None
    content_type: Optional[str] = None
    size: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_deleted: bool = Field(default=False)


class FileShare(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    file_id: int = Field(foreign_key="file.id")
    owner_id: int = Field(foreign_key="user.id")
    recipient_id: int = Field(foreign_key="user.id")
    shared_at: datetime = Field(default_factory=datetime.utcnow)
    bytes_transferred: int = 0
    message: Optional[str] = None


class Usage(SQLModel, table=True):
    # composite primary key: owner_id + recipient_id
    owner_id: int = Field(primary_key=True, index=True)
    recipient_id: int = Field(primary_key=True, index=True)

    total_bytes: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class RevokedToken(SQLModel, table=True):
    jti: str = Field(primary_key=True)
    expires_at: datetime


class ActivityLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    action: str
    details: Optional[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)
