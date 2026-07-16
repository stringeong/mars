"""UC-103 기기 등록/권한 설정, UC-104 기기 상태 확인.

기기 등록은 Worker CLI가 사용자 로그인 토큰으로 호출한다.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services.orchestrator import device_is_online

router = APIRouter(prefix="/devices", tags=["devices"])


def _to_out(device: models.Device, with_key: bool = False) -> dict:
    data = {
        "id": device.id,
        "name": device.name,
        "specs": device.specs or {},
        "allowed_folders": device.allowed_folders or [],
        "last_heartbeat": device.last_heartbeat,
        "online": device_is_online(device),
    }
    if with_key:
        data["api_key"] = device.api_key
    return data


@router.post("", response_model=schemas.DeviceRegisterOut, status_code=201)
def register_device(
    body: schemas.DeviceRegister,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    dup = (
        db.query(models.Device)
        .filter(models.Device.user_id == user.id, models.Device.name == body.name)
        .first()
    )
    if dup:
        raise HTTPException(409, "같은 이름의 기기가 이미 등록되어 있습니다.")  # e601
    device = models.Device(
        user_id=user.id,
        name=body.name,
        specs=body.specs,
        allowed_folders=body.allowed_folders,
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return _to_out(device, with_key=True)


@router.get("", response_model=list[schemas.DeviceOut])
def list_devices(
    user: models.User = Depends(get_current_user), db: Session = Depends(get_db)
):
    devices = db.query(models.Device).filter(models.Device.user_id == user.id).all()
    return [_to_out(d) for d in devices]


@router.patch("/{device_id}", response_model=schemas.DeviceOut)
def update_device(
    device_id: int,
    body: schemas.DeviceUpdate,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = db.get(models.Device, device_id)
    if device is None or device.user_id != user.id:
        raise HTTPException(404, "기기를 찾을 수 없습니다.")
    if body.name is not None:
        device.name = body.name
    if body.allowed_folders is not None:
        device.allowed_folders = body.allowed_folders
    db.commit()
    db.refresh(device)
    return _to_out(device)


@router.delete("/{device_id}", status_code=204)
def delete_device(
    device_id: int,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    device = db.get(models.Device, device_id)
    if device is None or device.user_id != user.id:
        raise HTTPException(404, "기기를 찾을 수 없습니다.")
    db.delete(device)
    db.commit()


#----------- Search Directory ----------
@router.get(
    "/{device_id}/directories",
    response_model=list[schemas.SharedDirectoryResponse],
)

def list_directories(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    device = (
        db.query(models.Device)
        .filter(
            models.Device.id == device_id,
            models.Device.user_id == current_user.id,
        )
        .first()
    )

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="기기를 찾을 수 없습니다.",
        )

    return (
        db.query(models.SharedDirectory)
        .filter(
            models.SharedDirectory.device_id == device_id,
            models.SharedDirectory.user_id == current_user.id,
        )
        .order_by(models.SharedDirectory.id)
        .all()
    )



#----------- Create Directory ----------
@router.post(
    "/{device_id}/directories",
    response_model=schemas.SharedDirectoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_directory(
    device_id: int,
    payload: schemas.SharedDirectoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    device = (
        db.query(models.Device)
        .filter(
            models.Device.id == device_id,
            models.Device.user_id == current_user.id,
        )
        .first()
    )

    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="기기를 찾을 수 없습니다.",
        )

    existing_alias = (
        db.query(models.SharedDirectory)
        .filter(
            models.SharedDirectory.user_id == current_user.id,
            models.SharedDirectory.alias == payload.alias,
        )
        .first()
    )

    if existing_alias:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 디렉토리 별명입니다.",
        )

    existing_path = (
        db.query(models.SharedDirectory)
        .filter(
            models.SharedDirectory.device_id == device_id,
            models.SharedDirectory.local_path == payload.local_path,
        )
        .first()
    )

    if existing_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="해당 기기에 이미 등록된 경로입니다.",
        )

    directory = models.SharedDirectory(
        user_id=current_user.id,
        device_id=device.id,
        alias=payload.alias,
        local_path=payload.local_path,
        permission=payload.permission,
    )

    db.add(directory)
    db.commit()
    db.refresh(directory)

    return directory


#----------- Update Directory ----------


@router.patch(
    "/{device_id}/directories/{directory_id}",
    response_model=schemas.SharedDirectoryResponse,
)
def update_directory(
    device_id: int,
    directory_id: int,
    payload: schemas.SharedDirectoryUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    directory = (
        db.query(models.SharedDirectory)
        .filter(
            models.SharedDirectory.id == directory_id,
            models.SharedDirectory.device_id == device_id,
            models.SharedDirectory.user_id == current_user.id,
        )
        .first()
    )

    if directory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="디렉토리를 찾을 수 없습니다.",
        )

    update_data = payload.model_dump(exclude_unset=True)

    if "alias" in update_data:
        duplicate_alias = (
            db.query(models.SharedDirectory)
            .filter(
                models.SharedDirectory.user_id == current_user.id,
                models.SharedDirectory.alias == update_data["alias"],
                models.SharedDirectory.id != directory_id,
            )
            .first()
        )

        if duplicate_alias:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 사용 중인 디렉토리 별명입니다.",
            )

    if "local_path" in update_data:
        duplicate_path = (
            db.query(models.SharedDirectory)
            .filter(
                models.SharedDirectory.device_id == device_id,
                models.SharedDirectory.local_path
                == update_data["local_path"],
                models.SharedDirectory.id != directory_id,
            )
            .first()
        )

        if duplicate_path:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="해당 기기에 이미 등록된 경로입니다.",
            )

    for field, value in update_data.items():
        setattr(directory, field, value)

    db.commit()
    db.refresh(directory)

    return directory


#----------- Delete Directory ----------
@router.delete(
    "/{device_id}/directories/{directory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_directory(
    device_id: int,
    directory_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    directory = (
        db.query(models.SharedDirectory)
        .filter(
            models.SharedDirectory.id == directory_id,
            models.SharedDirectory.device_id == device_id,
            models.SharedDirectory.user_id == current_user.id,
        )
        .first()
    )

    if directory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="디렉토리를 찾을 수 없습니다.",
        )

    directory.is_active = False

    db.commit()

    return None

