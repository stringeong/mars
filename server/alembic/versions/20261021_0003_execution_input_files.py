"""Record the input files each execution used, backfilling older executions."""

import json

from alembic import op
import sqlalchemy as sa

revision = "20261021_0003"
down_revision = "20261021_0002"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    return column in {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _as_dict(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value or {}


def upgrade() -> None:
    if not _has_column("executions", "input_files"):
        op.add_column("executions", sa.Column("input_files", sa.JSON(), nullable=True))

    # 이전 실행은 스냅샷에서 블록에 직접 붙은 파일을 찾아 이력을 채운다
    bind = op.get_bind()
    names = {
        row.id: row.original_name
        for row in bind.execute(sa.text("SELECT id, original_name FROM uploaded_files"))
    }
    rows = bind.execute(sa.text("SELECT id, graph_snapshot FROM executions WHERE input_files IS NULL")).all()
    for row in rows:
        graph = _as_dict(row.graph_snapshot)
        record = [
            {
                "kind": "node",
                "id": node["id"],
                "label": node.get("name") or node["id"],
                "node_ids": [node["id"]],
                "files": [
                    {"id": file_id, "name": names.get(file_id, f"파일 #{file_id}")}
                    for file_id in node.get("uploaded_file_ids") or []
                    if isinstance(file_id, int)
                ],
                "directories": [],
            }
            for node in graph.get("nodes", [])
            if node.get("type", "agent") == "agent" and node.get("uploaded_file_ids")
        ]
        bind.execute(
            sa.text("UPDATE executions SET input_files = :value WHERE id = :id"),
            {"value": json.dumps(record, ensure_ascii=False), "id": row.id},
        )


def downgrade() -> None:
    if _has_column("executions", "input_files"):
        with op.batch_alter_table("executions") as batch_op:
            batch_op.drop_column("input_files")
