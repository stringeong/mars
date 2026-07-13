"""security 모듈 검증 — 비밀번호 해시, JWT 발급/검증."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.config import ALGORITHM, SECRET_KEY
from app.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)


class TestPasswordHash:
    def test_roundtrip(self):
        hashed = hash_password("비밀번호123")
        assert hashed != "비밀번호123"
        assert verify_password("비밀번호123", hashed)

    def test_wrong_password_rejected(self):
        hashed = hash_password("비밀번호123")
        assert not verify_password("다른비밀번호", hashed)

    def test_hashes_are_salted(self):
        assert hash_password("같은입력") != hash_password("같은입력")


class TestAccessToken:
    def test_token_carries_user_id_and_expiry(self):
        token = create_access_token(42)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "42"
        assert payload["exp"] > datetime.now(timezone.utc).timestamp()


def expired_token(user_id):
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


class TestGetCurrentUser:
    def test_valid_token_returns_user(self, db, make_user):
        user = make_user()
        assert get_current_user(create_access_token(user.id), db) is user

    def test_garbage_token_rejected(self, db):
        with pytest.raises(HTTPException) as exc:
            get_current_user("이건.토큰이.아님", db)
        assert exc.value.status_code == 401

    def test_expired_token_rejected(self, db, make_user):
        user = make_user()
        with pytest.raises(HTTPException) as exc:
            get_current_user(expired_token(user.id), db)
        assert exc.value.status_code == 401

    def test_wrong_signing_key_rejected(self, db, make_user):
        user = make_user()
        forged = jwt.encode({"sub": str(user.id)}, "다른-키", algorithm=ALGORITHM)
        with pytest.raises(HTTPException) as exc:
            get_current_user(forged, db)
        assert exc.value.status_code == 401

    def test_non_numeric_sub_rejected(self, db):
        token = jwt.encode({"sub": "abc"}, SECRET_KEY, algorithm=ALGORITHM)
        with pytest.raises(HTTPException) as exc:
            get_current_user(token, db)
        assert exc.value.status_code == 401

    def test_missing_sub_rejected(self, db):
        token = jwt.encode({}, SECRET_KEY, algorithm=ALGORITHM)
        with pytest.raises(HTTPException) as exc:
            get_current_user(token, db)
        assert exc.value.status_code == 401

    def test_deleted_user_rejected(self, db):
        with pytest.raises(HTTPException) as exc:
            get_current_user(create_access_token(9999), db)
        assert exc.value.status_code == 401
