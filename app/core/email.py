from pathlib import Path
from datetime import datetime
import os

EMAIL_DIR = os.environ.get("EMAIL_LOG_DIR", "./logs/emails")
Path(EMAIL_DIR).mkdir(parents=True, exist_ok=True)

def send_local_email(to_email: str, subject: str, body: str):
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    safe_email = to_email.replace("@", "_at_")
    filename = Path(EMAIL_DIR) / f"email_{timestamp}_{safe_email}.txt"

    content = f"To: {to_email}\nSubject: {subject}\n\n{body}\n"
    filename.write_text(content)

    return str(filename)
