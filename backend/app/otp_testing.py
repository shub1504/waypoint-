import secrets
import time
from threading import Lock

OTP_TTL_SECONDS = 300
MAX_ATTEMPTS = 5

_pending = {}
_lock = Lock()


def generate_otp(email: str) -> str:
    email = email.strip().lower()
    code = f"{secrets.randbelow(1_000_000):06d}"

    with _lock:
        _pending[email] = {
            "code": code,
            "expires": time.time() + OTP_TTL_SECONDS,
            "attempts": 0,
        }

    # Development only: never log OTPs in production.
    print(f"[TEST OTP] {email}: {code} (expires in 5 minutes)")
    return code


def verify_otp(email: str, code: str) -> bool:
    email = email.strip().lower()

    with _lock:
        item = _pending.get(email)

        if not item or time.time() > item["expires"]:
            _pending.pop(email, None)
            return False

        item["attempts"] += 1

        if item["attempts"] > MAX_ATTEMPTS:
            _pending.pop(email, None)
            return False

        if secrets.compare_digest(item["code"], code.strip()):
            _pending.pop(email, None)
            return True

        return False