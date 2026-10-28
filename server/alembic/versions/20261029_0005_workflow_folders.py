"""Folders for sorting my workflows."""

from alembic import op
import sqlalchemy as sa

revision = "20261029_0005"
down_revision = "20261021_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    # 새 DB는 0001의 create_all이 이미 만든다
    if "workflow_folders" not in inspector.get_table_names():
        op.create_table(
            "workflow_folders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(length=60), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_workflow_folders_user_id", "workflow_folders", ["user_id"])
    if "folder_id" not in {column["name"] for column in inspector.get_columns("services")}:
        with op.batch_alter_table("services") as batch:
            batch.add_column(sa.Column("folder_id", sa.Integer(), nullable=True))
            batch.create_index("ix_services_folder_id", ["folder_id"])
            batch.create_foreign_key("fk_services_folder_id", "workflow_folders", ["folder_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("services") as batch:
        batch.drop_constraint("fk_services_folder_id", type_="foreignkey")
        batch.drop_index("ix_services_folder_id")
        batch.drop_column("folder_id")
    op.drop_table("workflow_folders")
