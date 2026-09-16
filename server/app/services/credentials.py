import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from ..config import CREDENTIAL_ENCRYPTION_KEY, SECRET_KEY


def _fernet() -> Fernet:
    if CREDENTIAL_ENCRYPTION_KEY:
        try:
            return Fernet(CREDENTIAL_ENCRYPTION_KEY.encode())
        except ValueError as exc:
            raise RuntimeError("MARS_CREDENTIAL_ENCRYPTION_KEY must be a Fernet key") from exc
    key = base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Stored credential cannot be decrypted") from exc
