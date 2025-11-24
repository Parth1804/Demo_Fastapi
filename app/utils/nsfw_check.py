from pathlib import Path
from typing import Tuple, Dict, Any
import logging
from PIL import Image
from app.core.config import settings

logger = logging.getLogger("shareledger.nsfw")
logger.setLevel(logging.INFO)

try:
    from nsfw_image_detector import NSFWDetector  # type: ignore
    _DETECTOR = NSFWDetector()
    _DETECTOR_NAME = "nsfw_image_detector"
except Exception as e:
    _DETECTOR = None
    _DETECTOR_NAME = None
    logger.info("nsfw_image_detector not available: %s", e)

NSFW_THRESHOLD = 0.7

def _is_image_file(path: Path) -> bool:
    try:
        suffix = path.suffix.lower()
        return suffix in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff")
    except Exception:
        return False

def predict_image(filepath: str) -> Dict[str, Any]:
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(filepath)

    # If file doesn't look like an image, return safe
    if not _is_image_file(p):
        return {"detector": None, "is_nsfw": False, "probs": {}}

    if _DETECTOR is not None:
        try:
            image = Image.open(str(p)).convert("RGB")
            is_nsfw = _DETECTOR.is_nsfw(image)
            probs = _DETECTOR.predict_proba(image)
            # compute a simple nsfw score from probs if needed
            score = 0.0
            for k, v in (probs or {}).items():
                if k.lower() in ("porn", "sexy", "nsfw", "explicit"):
                    score += float(v)
            if score == 0.0 and isinstance(is_nsfw, bool):
                score = 1.0 if is_nsfw else 0.0
            return {"detector": _DETECTOR_NAME, "is_nsfw": score >= NSFW_THRESHOLD, "probs": probs}
        except Exception as exc:
            logger.exception("Primary detector failed: %s", exc)
            # conservative or permissive fallback handled by caller
            raise

    # no detector available -> behave according to settings
    if settings.nsfw_detector != "enabled":
        return {"detector": None, "is_nsfw": False, "probs": {}}

    raise RuntimeError("NSFW detector enabled in config but no detector installed")
