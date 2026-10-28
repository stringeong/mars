"""내 워크플로우 폴더. 폴더는 분류용이라 지워도 안의 워크플로우는 미분류로 남는다."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user

router = APIRouter(prefix="/folders", tags=["folders"])


def get_owned_folder(folder_id: int, user: models.User, db: Session) -> models.WorkflowFolder:
    folder = db.get(models.WorkflowFolder, folder_id)
    if folder is None or folder.user_id != user.id:
        raise HTTPException(404, "폴더를 찾을 수 없습니다.")
    return folder


def _check_unique(name: str, user: models.User, db: Session, exclude: int | None = None) -> str:
    name = name.strip()
    if not name:
        raise HTTPException(422, "폴더 이름을 입력해 주세요.")
    query = db.query(models.WorkflowFolder).filter(models.WorkflowFolder.user_id == user.id, models.WorkflowFolder.name == name)
    if exclude is not None:
        query = query.filter(models.WorkflowFolder.id != exclude)
    if query.first():
        raise HTTPException(409, "같은 이름의 폴더가 이미 있습니다.")
    return name


@router.get("", response_model=list[schemas.FolderOut])
def list_folders(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(models.WorkflowFolder)
        .filter(models.WorkflowFolder.user_id == user.id)
        .order_by(models.WorkflowFolder.name)
        .all()
    )


@router.post("", response_model=schemas.FolderOut, status_code=201)
def create_folder(body: schemas.FolderIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    folder = models.WorkflowFolder(user_id=user.id, name=_check_unique(body.name, user, db))
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


@router.put("/{folder_id}", response_model=schemas.FolderOut)
def rename_folder(
    folder_id: int,
    body: schemas.FolderIn,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    folder = get_owned_folder(folder_id, user, db)
    folder.name = _check_unique(body.name, user, db, exclude=folder.id)
    db.commit()
    db.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=204)
def delete_folder(folder_id: int, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    folder = get_owned_folder(folder_id, user, db)
    db.query(models.Service).filter(models.Service.folder_id == folder.id).update({"folder_id": None}, synchronize_session=False)
    db.delete(folder)
    db.commit()
