import hashlib
import hmac
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from ..config import settings

password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerifyMismatchError, VerificationError):
        return False


def _signature(session_id: UUID) -> str:
    return hmac.new(
        settings.session_secret.encode("utf-8"), str(session_id).encode("ascii"), hashlib.sha256
    ).hexdigest()


def sign_session_id(session_id: UUID) -> str:

    return f"{session_id}.{_signature(session_id)}"


def read_session_id(cookie: str | None) -> UUID | None:

    if not cookie or "." not in cookie:
        return None
    raw_id, signature = cookie.rsplit(".", 1)
    try:
        session_id = UUID(raw_id)
    except ValueError:
        return None
    if not hmac.compare_digest(signature, _signature(session_id)):
        return None
    return session_id
