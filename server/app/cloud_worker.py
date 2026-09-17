"""Dedicated process for cloud LLM tasks."""

import logging
import os
import time

from sqlalchemy.exc import SQLAlchemyError

from .database import SessionLocal
from .services.cloud_executor import process_one_ready_cloud_task

logging.basicConfig(level=os.getenv("MARS_LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)
POLL_SECONDS = max(0.2, float(os.getenv("MARS_CLOUD_POLL_SECONDS", "1")))


def main() -> None:
    logger.info("M.A.R.S cloud worker started")
    while True:
        db = SessionLocal()
        try:
            processed = process_one_ready_cloud_task(db)
        except SQLAlchemyError:
            db.rollback()
            logger.exception("Cloud worker database error")
            processed = False
        except Exception:
            db.rollback()
            logger.exception("Unexpected cloud worker error")
            processed = False
        finally:
            db.close()
        if not processed:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
