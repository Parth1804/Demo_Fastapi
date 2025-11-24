from pydantic import BaseSettings
import os

class Settings(BaseSettings):
    app_name: str = "ShareLedger"
    secret_key: str
    access_token_expire_minutes: int = 60
    database_url: str

    upload_dir: str = "./uploads"
    email_log_dir: str = "./logs/emails"

    max_upload_size_bytes: int = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", 52428800))

    nsfw_detector: str = os.environ.get("NSFW_DETECTOR", "disabled")

    class Config:
        env_file = ".env"

settings = Settings()
