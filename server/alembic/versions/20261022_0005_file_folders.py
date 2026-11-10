"""Add virtual folders to the uploaded file vault."""

from alembic import op
import sqlalchemy as sa

revision = "20261022_0005"
down_revision = "20261029_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = sa.inspect(bind).get_table_names()
    if "file_folders" not in tables:
        op.create_table(
            "file_folders",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_file_folders_user_id", "file_folders", ["user_id"])
    columns = {column["name"] for column in sa.inspect(bind).get_columns("uploaded_files")}
    if "folder_id" not in columns:
        with op.batch_alter_table("uploaded_files") as batch_op:
            batch_op.add_column(sa.Column("folder_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key("fk_uploaded_files_folder_id_file_folders", "file_folders", ["folder_id"], ["id"])
            batch_op.create_index("ix_uploaded_files_folder_id", ["folder_id"])


def downgrade() -> None:
    with op.batch_alter_table("uploaded_files") as batch_op:
        batch_op.drop_constraint("fk_uploaded_files_folder_id_file_folders", type_="foreignkey")
        batch_op.drop_index("ix_uploaded_files_folder_id")
        batch_op.drop_column("folder_id")
    op.drop_table("file_folders")
