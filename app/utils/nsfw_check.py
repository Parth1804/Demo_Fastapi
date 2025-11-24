from pathlib import Path
from typing import Tuple, Dict, Any
import logging

from PIL import Image

from app.core.config import settings

logger = logging.getLogger("shareledger.nsfw")
logger.setLevel(logging.INFO)

# Try primary detector first (nsfw_image_detector)
try:
    from nsfw_image_detector import NSFWDetector  # type: ignore

    _DETECTOR = NSFWDetector()
    _DETECTOR_NAME = "nsfw_image_detector"
except Exception as e:
    _DETECTOR = None
    _DETECTOR_NAME = None
    logger.info("nsfw_image_detector not available: %s", e)

# Optional fallback using opennsfw-standalone (ONNX runtime)
try:
    import opennsfw_standalone  # type: ignore
    from opennsfw_standalone import OpenNSFW  # type: ignore

    _ONNX = OpenNSFW()
    _ONNX_NAME = "opennsfw-standalone"
except Exception:
    _ONNX = None
    _ONNX_NAME = None


# Threshold for classifying NSFW. You can tune this (0..1).
NSFW_THRESHOLD = 0.7


def _predict_with_primary(image: Image.Image) -> Tuple[bool, Dict[str, float]]:
    """
    Use nsfw_image_detector NSFWDetector instance.
    Returns (is_nsfw, probs_dict).
    """
    global _DETECTOR
    if _DETECTOR is None:
        raise RuntimeError("Primary nsfw detector not available")

    try:
        is_nsfw = _DETECTOR.is_nsfw(image)  # returns bool
        probs = _DETECTOR.predict_proba(image)  # returns dict of category probabilities
        # If the library returns classes like {'nsfw': 0.9} adapt below; otherwise check 'porn'/'sexy'
        # We'll treat sum of explicit categories as nsfw score if present.
        # Normalize handling:
        score = 0.0
        # some detectors provide 'porn' and 'sexy', or a single 'nsfw' flag.
        for k, v in probs.items():
            k_lower = k.lower()
            if k_lower in ("porn", "sexy", "nsfw", "explicit"):
                score += float(v)
        # fallback if detector only returned is_nsfw boolean
        if score == 0.0 and isinstance(is_nsfw, bool):
            score = 1.0 if is_nsfw else 0.0
        return (score >= NSFW_THRESHOLD, probs)
    except Exception as exc:
        logger.exception("Primary detector failed: %s", exc)
        raise


def _predict_with_onnx(filepath: str) -> Tuple[bool, Dict[str, float]]:
    """
    Use onnx-based detector (opennsfw-standalone) if available.
    Returns (is_nsfw, probs_dict).
    """
    global _ONNX
    if _ONNX is None:
        raise RuntimeError("ONNX detector not available")
    try:
        res = _ONNX.predict(filepath)  # depends on opennsfw API
        # opennsfw may return a single score between 0..1 where higher == more NSFW
        # we'll convert to dict for compatibility
        if isinstance(res, (float, int)):
            score = float(res)
            probs = {"nsfw_score": score}
        elif isinstance(res, dict):
            probs = res
            score = float(res.get("nsfw_score", max(res.values())))
        else:
            probs = {"nsfw_score": float(res)}
            score = float(res)
        return (score >= NSFW_THRESHOLD, probs)
    except Exception as exc:
        logger.exception("ONNX detector failed: %s", exc)
        raise


def predict_image(filepath: str) -> Dict[str, Any]:
    """
    Predicts NSFW score and returns a dict:
    {
      "detector": "<name>",
      "is_nsfw": True/False,
      "probs": {...}
    }
    """
    p = Path(filepath)
    if not p.exists():
        raise FileNotFoundError(filepath)

    # Try primary (image) detector
    if _DETECTOR is not None:
        try:
            image = Image.open(str(p)).convert("RGB")
            is_nsfw, probs = _predict_with_primary(image)
            return {"detector": _DETECTOR_NAME, "is_nsfw": is_nsfw, "probs": probs}
        except Exception:
            # fallthrough to ONNX if available
            logger.info("Primary detector failed, trying ONNX fallback")

    if _ONNX is not None:
        is_nsfw, probs = _predict_with_onnx(str(p))
        return {"detector": _ONNX_NAME, "is_nsfw": is_nsfw, "probs": probs}

    # If no detectors available, behave according to config flag:
    if settings.nsfw_detector != "enabled":
        # If disabled, always safe
        return {"detector": None, "is_nsfw": False, "probs": {}}

    # If enabled but no library available, raise so caller can block or log appropriately
    raise RuntimeError("NSFW detector enabled in config but no detector libraries are installed")


def is_nsfw(filepath: str) -> bool:
    """
    Convenience wrapper returning boolean.
    """
    try:
        res = predict_image(filepath)
        return bool(res.get("is_nsfw", False))
    except Exception as e:
        # On error, conservative policy: treat as NSFW (safer) OR you can choose to treat as safe.
        # We'll choose conservative: log and return True -> block upload.
        logger.exception("Error predicting NSFW for %s: %s", filepath, e)
        return True
