"""이벤트 로그 기록 헬퍼 (NF-205/NF-207).

커밋은 하지 않는다 — 호출한 쪽의 트랜잭션에 편승해, 본 작업과 로그가
함께 저장되거나 함께 롤백되게 한다.
"""

from sqlalchemy.orm import Session

from .. import models


def record(db: Session, user_id: int | None, event_type: str, detail: str = "") -> None:
    db.add(models.EventLog(user_id=user_id, event_type=event_type, detail=detail))
