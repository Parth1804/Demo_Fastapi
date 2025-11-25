from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class Token(BaseModel):
    access_token: str
    token_type: str


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str


class UserRead(BaseModel):
    id: int
    email: EmailStr
    username: str
    role: str
    created_at: datetime

    class Config:
        orm_mode = True


class FileUploadResp(BaseModel):
    id: int
    filename: str
    size: int
    stored_path: str
    cloud_url: Optional[str] = None
    content_type: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True


class ShareReq(BaseModel):
    file_id: int
    recipient_email: EmailStr
    message: Optional[str] = None


class UsageResp(BaseModel):
    owner_id: int
    recipient_id: int
    total_bytes: int

    class Config:
        orm_mode = True
