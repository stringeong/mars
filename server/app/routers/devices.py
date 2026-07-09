"""UC-103 기기 등록/권한 설정, UC-104 기기 상태 확인.

기기 등록은 Worker CLI가 사용자 로그인 토큰으로 호출한다.
"""

from fastapi import APIRouter, Depends, HTTPException
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
