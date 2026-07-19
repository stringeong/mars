"""UC-101 회원가입, UC-102 로그인, 회원정보 수정, 활동 로그 조회."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import create_access_token, get_current_user, hash_password, verify_password
from ..services import events

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.UserOut, status_code=201)
def register(body: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.username == body.username).first():
        raise HTTPException(409, "이미 사용 중인 아이디입니다.")  # e201
    if db.query(models.User).filter(models.User.email == body.email).first():
        raise HTTPException(409, "이미 사용 중인 이메일입니다.")  # e202
    user = models.User(
        email=body.email,
        username=body.username,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.flush()
    events.record(db, user.id, "회원가입")
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == form.username).first()
    if user is None or not verify_password(form.password, user.password_hash):
        # NF-205: 비정상 로그인 시도 기록 (존재하지 않는 아이디는 user_id 없이)
        events.record(
            db, user.id if user else None, "로그인 실패", f"아이디: {form.username}"
        )
        db.commit()
        raise HTTPException(401, "아이디 또는 비밀번호가 일치하지 않습니다.")  # e301
    events.record(db, user.id, "로그인 성공")
    db.commit()
    return schemas.Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=schemas.UserOut)
def me(user: models.User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=schemas.UserOut)
def update_me(
    body: schemas.UserUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """회원정보 수정 (이메일·비밀번호). 본인 확인을 위해 현재 비밀번호 필요."""
    if not verify_password(body.current_password, user.password_hash):
        events.record(db, user.id, "회원정보 수정 실패", "현재 비밀번호 불일치")
        db.commit()
        raise HTTPException(401, "현재 비밀번호가 일치하지 않습니다.")
    changed = []
    if body.email is not None and body.email != user.email:
        dup = db.query(models.User).filter(models.User.email == body.email).first()
        if dup:
            raise HTTPException(409, "이미 사용 중인 이메일입니다.")
        user.email = body.email
        changed.append("이메일")
    if body.new_password:
        user.password_hash = hash_password(body.new_password)
        changed.append("비밀번호")
    if changed:
        events.record(db, user.id, "회원정보 수정", ", ".join(changed) + " 변경")
    db.commit()
    db.refresh(user)
    return user


@router.get("/events", response_model=list[schemas.EventOut])
def list_events(
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """내 계정의 최근 활동 로그 (NF-207). 최근 100건."""
    return (
        db.query(models.EventLog)
        .filter(models.EventLog.user_id == user.id)
        .order_by(models.EventLog.created_at.desc(), models.EventLog.id.desc())
        .limit(100)
        .all()
    )
