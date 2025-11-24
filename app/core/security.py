from jose import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext
from app.core.config import settings
import uuid

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expire = datetime.utcnow() + timedelta(
        minutes=(expires_minutes or settings.access_token_expire_minutes)
    )
    jti = str(uuid.uuid4())
    payload = {"sub": subject, "exp": expire, "jti": jti}
    token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
    return token


def decode_token(token: str) -> dict:
    payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    return payload
