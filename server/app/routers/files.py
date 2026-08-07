"""User file vault for workflow input attachments."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import UPLOAD_DIR
from ..database import get_db
from ..security import get_current_user

router = APIRouter(prefix="/files", tags=["files"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _owned_file(file_id: int, user: models.User, db: Session) -> models.UploadedFile:
    uploaded = db.get(models.UploadedFile, file_id)
    if uploaded is None or uploaded.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found.")
    return uploaded


@router.get("", response_model=list[schemas.UploadedFileOut])
def list_files(
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return (
        db.query(models.UploadedFile)
        .filter(models.UploadedFile.user_id == user.id)
        .order_by(models.UploadedFile.created_at.desc())
        .all()
    )


@router.post("", response_model=schemas.UploadedFileOut, status_code=status.HTTP_201_CREATED)
def upload_file(
    file: UploadFile = File(...),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    original_name = Path(file.filename or "upload").name
    if not original_name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A file name is required.")
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{Path(original_name).suffix.lower()}"
    destination = UPLOAD_DIR / stored_name
    size_bytes = 0
    try:
        with destination.open("wb") as target:
            while chunk := file.file.read(1024 * 1024):
                size_bytes += len(chunk)
                if size_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Files must be 50 MB or smaller.")
                target.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()
    uploaded = models.UploadedFile(
        user_id=user.id,
        original_name=original_name,
        stored_name=stored_name,
        content_type=file.content_type,
        size_bytes=size_bytes,
    )
    db.add(uploaded)
    db.commit()
    db.refresh(uploaded)
    return uploaded


@router.get("/{file_id}/download")
def download_file(
    file_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uploaded = _owned_file(file_id, user, db)
    path = UPLOAD_DIR / uploaded.stored_name
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stored file not found.")
    return FileResponse(path, media_type=uploaded.content_type, filename=uploaded.original_name)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uploaded = _owned_file(file_id, user, db)
    (UPLOAD_DIR / uploaded.stored_name).unlink(missing_ok=True)
    db.delete(uploaded)
    db.commit()
