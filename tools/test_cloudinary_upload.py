# tools/test_cloudinary_upload.py
import argparse
import asyncio
from app.utils.storage import upload_file_to_cloudinary
from app.core.config import settings


def parse_args():
    p = argparse.ArgumentParser(description="Test Cloudinary upload")
    p.add_argument("--path", help="Path to local file to upload", default="uploads/test_upload.png")
    return p.parse_args()


async def run(path: str):
    print("Cloudinary configured:", settings.cloudinary_cloud_name, settings.cloudinary_api_key is not None)
    folder = f"{settings.cloudinary_upload_folder}/test"
    res = await upload_file_to_cloudinary(path, public_id=None, folder=folder)
    print("Upload result keys:", list(res.keys()))
    print("secure_url:", res.get("secure_url"))
    print(res)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args.path))
