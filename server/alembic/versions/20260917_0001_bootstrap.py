"""Bootstrap schema and hash legacy Worker credentials."""

import hashlib

from alembic import op
import sqlalchemy as sa

from app.database import Base
from app import models  # noqa: F401

revision = "20260917_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    had_devices = "devices" in inspector.get_table_names()
    old_columns = {column["name"] for column in inspector.get_columns("devices")} if had_devices else set()

    Base.metadata.create_all(bind=bind)
    if had_devices and "api_key_hash" not in old_columns:
        op.add_column("devices", sa.Column("api_key_hash", sa.String(length=64), nullable=True))

    rows = bind.execute(sa.text("SELECT id, api_key, api_key_hash FROM devices")).mappings()
    for row in rows:
        current = row["api_key_hash"]
        digest = current or hashlib.sha256((row["api_key"] or "").encode()).hexdigest()
        bind.execute(
            sa.text("UPDATE devices SET api_key = :digest, api_key_hash = :digest WHERE id = :id"),
            {"digest": digest, "id": row["id"]},
        )

    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("devices")}
    if "ix_devices_api_key_hash" not in indexes:
        op.create_index("ix_devices_api_key_hash", "devices", ["api_key_hash"], unique=True)


def downgrade() -> None:
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("devices")}
    if "ix_devices_api_key_hash" in indexes:
        op.drop_index("ix_devices_api_key_hash", table_name="devices")
    with op.batch_alter_table("devices") as batch_op:
        batch_op.drop_column("api_key_hash")
