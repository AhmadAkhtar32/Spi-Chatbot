"""Short-lived presenter sessions for the fictional SPIA demonstration.

Production authentication must use a verified SPIA launch/session instead.
No PIN or signing secret is stored in frontend code or the demo dataset.
"""

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import time

from demo_policy import AccessDenied, authorize_surface, get_demo_user


SESSION_SECONDS = 60 * 60
VALID_SURFACES = {"spia_tsplus", "mobile"}


def _settings() -> tuple[bytes, str, str]:
    secret = os.environ.get("DEMO_SESSION_SECRET", "")
    spia_pin = os.environ.get("DEMO_SPIA_PIN", "")
    mobile_pin = os.environ.get("DEMO_MOBILE_PIN", "")
    if (len(secret) < 32 or len(spia_pin) < 12 or len(mobile_pin) < 12
            or not spia_pin.isascii() or not mobile_pin.isascii()):
        raise RuntimeError("Set DEMO_SESSION_SECRET (32+ chars) and two demo PINs (12+ chars).")
    if hmac.compare_digest(spia_pin, mobile_pin):
        raise RuntimeError("DEMO_SPIA_PIN and DEMO_MOBILE_PIN must be different.")
    return secret.encode("utf-8"), spia_pin, mobile_pin


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _signature(secret: bytes, payload: str) -> str:
    return _b64encode(hmac.new(secret, payload.encode("ascii"), hashlib.sha256).digest())


def issue_demo_session(user_id: str, surface: str, presenter_pin: str) -> str:
    """The presenter chooses a fictional persona after proving the demo PIN."""
    secret, spia_pin, mobile_pin = _settings()
    if surface not in VALID_SURFACES:
        raise AccessDenied("Demo session unavailable")
    expected_pin = spia_pin if surface == "spia_tsplus" else mobile_pin
    if not isinstance(presenter_pin, str) or not hmac.compare_digest(presenter_pin, expected_pin):
        raise AccessDenied("Demo session unavailable")

    user = get_demo_user(user_id)
    authorize_surface(user, surface)
    now = int(time.time())
    payload = _b64encode(json.dumps({
        "v": 1, "sub": user["id"], "surface": surface,
        "iat": now, "exp": now + SESSION_SECONDS,
    }, separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{_signature(secret, payload)}"


def verify_demo_session(token: str) -> tuple[dict, str]:
    """Return server-side user data and the signed surface, or deny."""
    secret, _, _ = _settings()
    if not isinstance(token, str) or len(token) > 4096:
        raise AccessDenied("Demo session unavailable")
    parts = token.split(".")
    if (len(parts) != 2
            or re.fullmatch(r"[A-Za-z0-9_-]{1,4000}", parts[0]) is None
            or re.fullmatch(r"[A-Za-z0-9_-]{43}", parts[1]) is None
            or not hmac.compare_digest(parts[1], _signature(secret, parts[0]))):
        raise AccessDenied("Demo session unavailable")
    try:
        payload = json.loads(_b64decode(parts[0]))
        now = int(time.time())
        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise ValueError("Unexpected token format")
        issued = payload["iat"]
        expires = payload["exp"]
        surface = payload["surface"]
        user_id = payload["sub"]
        if (type(issued) is not int or type(expires) is not int
                or not isinstance(surface, str) or not isinstance(user_id, str)
                or surface not in VALID_SURFACES
                or issued > now + 60 or expires <= now
                or expires - issued != SESSION_SECONDS):
            raise ValueError("Invalid or expired demo session")
        user = get_demo_user(user_id)
        authorize_surface(user, surface)
        return user, surface
    except (ValueError, KeyError, TypeError, UnicodeError, binascii.Error):
        raise AccessDenied("Demo session unavailable") from Nones