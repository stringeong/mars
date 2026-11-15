"""Keep what a finished task left out of its input (cut files, context overflow)."""

from alembic import op
import sqlalchemy as sa

revision = "20261115_0007"
down_revision = "20261022_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("tasks")}
    if "notice" not in columns:
        op.add_column("tasks", sa.Column("notice", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_column("notice")
