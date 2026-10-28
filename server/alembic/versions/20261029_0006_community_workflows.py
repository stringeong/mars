"""Share workflows to the community examples."""

from alembic import op
import sqlalchemy as sa

revision = "20261029_0006"
down_revision = "20261029_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 새 DB는 0001의 create_all이 이미 만든다
    if "community_workflows" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "community_workflows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_id", sa.Integer(), sa.ForeignKey("services.id"), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=60), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("graph", sa.JSON(), nullable=False),
        sa.Column("import_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_community_workflows_user_id", "community_workflows", ["user_id"])


def downgrade() -> None:
    op.drop_table("community_workflows")
