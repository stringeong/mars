"""Record which model generated each workflow and copy it into execution history."""

from alembic import op
import sqlalchemy as sa

revision = "20261021_0002"
down_revision = "20260917_0001"
branch_labels = None
depends_on = None

TABLES = ("services", "executions")


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # 새 DB는 bootstrap의 create_all이 이미 컬럼을 만들었으므로 없는 경우에만 추가한다
    for table in TABLES:
        if not _has_column(table, "generation_info"):
            op.add_column(table, sa.Column("generation_info", sa.JSON(), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        if _has_column(table, "generation_info"):
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_column("generation_info")
