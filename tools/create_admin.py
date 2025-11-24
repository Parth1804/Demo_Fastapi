import argparse
import asyncio
import sys
from pathlib import Path

# Ensure project root is importable when running this script directly
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.security import get_password_hash
from app.db.session import engine
from sqlmodel.ext.asyncio.session import AsyncSession
from app.crud import create_user, get_user_by_email


async def create_or_promote_admin(email: str, username: str, password: str) -> dict:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        # If a user with this email exists, promote to admin
        existing = await get_user_by_email(session, email)
        if existing:
            existing.role = "admin"
            await session.commit()
            return {"email": email, "username": existing.username, "password": "(unchanged)", "promoted": True}

        hashed = get_password_hash(password)
        user = await create_user(session, email=email, username=username, hashed_password=hashed, role="admin")
        return {"email": user.email, "username": user.username, "password": password, "promoted": False}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create or promote an admin user")
    p.add_argument("--email", default="admin@example.com", help="Admin email")
    p.add_argument("--username", default="admin", help="Admin username")
    p.add_argument("--password", default="Admin@123", help="Admin password")
    return p.parse_args()


def main():
    args = parse_args()
    result = asyncio.run(create_or_promote_admin(args.email, args.username, args.password))
    if result.get("promoted"):
        print(f"Promoted existing user '{result['email']}' to admin (username='{result['username']}')")
    else:
        print(f"Created admin: {result['email']} (username='{result['username']}')")
    print("Credentials:")
    print(f"  email: {result['email']}")
    print(f"  username: {result['username']}")
    print(f"  password: {result['password']}")


if __name__ == "__main__":
    main()
# email: you@domain.com        
#   username: yourname
#   password: S3cure!