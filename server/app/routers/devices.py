"""UC-103 기기 등록/권한 설정, UC-104 기기 상태 확인.

기기 등록은 Worker CLI가 사용자 로그인 토큰으로 호출한다.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..security import get_current_user
from ..services import directory_access
from ..services.orchestrator import device_is_online

router = APIRouter(prefix="/devices", tags=["devices"])


def _to_out(device: models.Device, with_key: bool = False) -> dict:
    specs = device.specs or {}
    data = {
        "id": device.id,
        "name": device.name,
        "specs": specs,
        "resource_limits": specs.get("resource_limits") or {},
        "last_heartbeat": device.last_heartbeat,
        "online": device_is_online(device),
    }
    if with_key:
        data["api_key"] = device.api_key
    return data


def _directory_out(directory: models.SharedDirectory, local_path: str) -> dict:
    return {
        "id": directory.id,
        "user_id": directory.user_id,
        "device_id": directory.device_id,
        "alias": directory.alias,
        "local_path": local_path,
        "permission": directory.permission,
        "is_active": directory.is_active,
        "created_at": directory.created_at,
        "updated_at": directory.updated_at,
    }


@router.post("", response_model=schemas.DeviceRegisterOut, status_code=201)
def register_device(
    body: schemas.DeviceRegister,
    response: Response,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(models.Device)
        .filter(models.Device.user_id == user.id, models.Device.name == body.name)
        .first()
    )
    if existing:
        # Reconnect the logical Worker so assignments and mounts keep their device ID.
        existing.specs = {**(existing.specs or {}), **body.specs}
        existing.api_key = secrets.token_hex(24)
        db.commit()
        db.refresh(existing)
        response.status_code = status.HTTP_200_OK
        return _to_out(existing, with_key=True)
    device = models.Device(
        user_id=user.id,
        name=body.name,
        specs=body.specs,
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
        duplicate = (
            db.query(models.Device)
            .filter(
                models.Device.user_id == user.id,
                models.Device.name == body.name,
                models.Device.id != device.id,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(409, "같은 이름의 기기가 이미 등록되어 있습니다.")
        device.name = body.name
    if body.resource_limits is not None:
        device.specs = {
            **(device.specs or {}),
            "resource_limits": body.resource_limits.model_dump(exclude_none=True),
        }
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

    directories = (
        db.query(models.SharedDirectory)
        .filter(models.SharedDirectory.user_id == current_user.id)
        .order_by(models.SharedDirectory.id)
        .all()
    )
    mounts = (
        db.query(models.DirectoryMount)
        .filter(models.DirectoryMount.device_id == device_id)
        .all()
    )
    paths = {mount.directory_id: mount.local_path for mount in mounts}
    return [
        _directory_out(directory, paths.get(directory.id, directory.local_path))
        for directory in directories
        if directory.device_id == device_id or directory.id in paths
    ]



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
        existing_mount = (
            db.query(models.DirectoryMount)
            .filter(
                models.DirectoryMount.directory_id == existing_alias.id,
                models.DirectoryMount.device_id == device_id,
            )
            .first()
        )
        if existing_alias.device_id == device_id or existing_mount is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이 Worker에 이미 등록된 디렉토리 별명입니다.",
            )
        path_in_use = (
            db.query(models.SharedDirectory)
            .filter(
                models.SharedDirectory.device_id == device_id,
                models.SharedDirectory.local_path == payload.local_path,
            )
            .first()
            or db.query(models.DirectoryMount)
            .filter(
                models.DirectoryMount.device_id == device_id,
                models.DirectoryMount.local_path == payload.local_path,
            )
            .first()
        )
        if path_in_use:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="해당 기기에 이미 등록된 경로입니다.",
            )
        db.add(models.DirectoryMount(
            directory_id=existing_alias.id,
            device_id=device_id,
            local_path=payload.local_path,
        ))
        db.commit()
        db.refresh(existing_alias)
        return _directory_out(existing_alias, payload.local_path)

    existing_path = (
        db.query(models.SharedDirectory)
        .filter(
            models.SharedDirectory.device_id == device_id,
            models.SharedDirectory.local_path == payload.local_path,
        )
        .first()
    )
    existing_mount_path = (
        db.query(models.DirectoryMount)
        .filter(
            models.DirectoryMount.device_id == device_id,
            models.DirectoryMount.local_path == payload.local_path,
        )
        .first()
    )

    if existing_path or existing_mount_path:
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

    return _directory_out(directory, directory.local_path)


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
    device = db.get(models.Device, device_id)
    if device is None or device.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="기기를 찾을 수 없습니다.",
        )

    directory = (
        db.query(models.SharedDirectory)
        .filter(
            models.SharedDirectory.id == directory_id,
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
    mount = (
        db.query(models.DirectoryMount)
        .filter(
            models.DirectoryMount.directory_id == directory_id,
            models.DirectoryMount.device_id == device_id,
        )
        .first()
    )
    if directory.device_id != device_id and mount is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="이 기기에 등록된 디렉토리를 찾을 수 없습니다.",
        )

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
        duplicate_directory_path = (
            db.query(models.SharedDirectory)
            .filter(
                models.SharedDirectory.device_id == device_id,
                models.SharedDirectory.local_path
                == update_data["local_path"],
                models.SharedDirectory.id != directory_id,
            )
            .first()
        )
        duplicate_mount_path = (
            db.query(models.DirectoryMount)
            .filter(
                models.DirectoryMount.device_id == device_id,
                models.DirectoryMount.local_path == update_data["local_path"],
                models.DirectoryMount.directory_id != directory_id,
            )
            .first()
        )

        if duplicate_directory_path or duplicate_mount_path:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="해당 기기에 이미 등록된 경로입니다.",
            )

    for field, value in update_data.items():
        if field == "local_path":
            continue
        setattr(directory, field, value)

    if "local_path" in update_data:
        if directory.device_id == device_id:
            directory.local_path = update_data["local_path"]
        elif mount is not None:
            mount.local_path = update_data["local_path"]
        else:
            db.add(models.DirectoryMount(
                directory_id=directory.id,
                device_id=device_id,
                local_path=update_data["local_path"],
            ))

    db.commit()
    db.refresh(directory)

    local_path = (
        update_data.get("local_path")
        or (mount.local_path if mount is not None else directory.local_path)
    )
    return _directory_out(directory, local_path)


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
    device = db.get(models.Device, device_id)
    if device is None or device.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="기기를 찾을 수 없습니다.",
        )

    directory = (
        db.query(models.SharedDirectory)
        .filter(
            models.SharedDirectory.id == directory_id,
            models.SharedDirectory.user_id == current_user.id,
        )
        .first()
    )

    if directory is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="디렉토리를 찾을 수 없습니다.",
        )

    mount = (
        db.query(models.DirectoryMount)
        .filter(
            models.DirectoryMount.directory_id == directory_id,
            models.DirectoryMount.device_id == device_id,
        )
        .first()
    )
    if directory.device_id != device_id:
        if mount is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="이 기기에 등록된 디렉토리를 찾을 수 없습니다.",
            )
        db.delete(mount)
    else:
        replacement = (
            db.query(models.DirectoryMount)
            .filter(models.DirectoryMount.directory_id == directory_id)
            .order_by(models.DirectoryMount.id)
            .first()
        )
        if replacement is None:
            directory.is_active = False
        else:
            directory.device_id = replacement.device_id
            directory.local_path = replacement.local_path
            db.delete(replacement)

    db.commit()

    return None


@router.post(
    "/{device_id}/directories/{directory_id}/inspections",
    response_model=schemas.DirectoryInspectionOut,
    status_code=status.HTTP_201_CREATED,
)
def request_directory_inspection(
    device_id: int,
    directory_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    device = db.get(models.Device, device_id)
    directory = db.get(models.SharedDirectory, directory_id)
    if device is None or device.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="기기를 찾을 수 없습니다.")
    if directory is None or directory.user_id != current_user.id or not directory.is_active:
        raise HTTPException(status_code=404, detail="활성 디렉터리를 찾을 수 없습니다.")
    paths = directory_access.local_paths_for_device(db, device_id, [directory_id])
    if paths is None:
        raise HTTPException(
            status_code=422,
            detail="이 Worker에 등록된 디렉터리 경로가 없습니다.",
        )
    inspection = models.DirectoryInspection(
        user_id=current_user.id,
        directory_id=directory_id,
        device_id=device_id,
        local_path=paths[0],
    )
    db.add(inspection)
    db.commit()
    db.refresh(inspection)
    return inspection


@router.get(
    "/{device_id}/directories/{directory_id}/inspections/latest",
    response_model=schemas.DirectoryInspectionOut | None,
)
def get_latest_directory_inspection(
    device_id: int,
    directory_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.DirectoryInspection)
        .filter(
            models.DirectoryInspection.user_id == current_user.id,
            models.DirectoryInspection.device_id == device_id,
            models.DirectoryInspection.directory_id == directory_id,
        )
        .order_by(models.DirectoryInspection.id.desc())
        .first()
    )

