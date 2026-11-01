"""execution_target soft delete (M3.6 GAP-42, D29/D30/D31)

为 execution_target 增加软删三列 + 软删唯一键，与 element / test_suite 同款：
* ``is_deleted`` / ``deleted_at`` / ``deleted_seq``（0=未删；删除时置为自身 id）
* ``uk_target_name (project_id, name, deleted_seq)``：项目内活记录 name 唯一，
  软删行 deleted_seq=id 互不冲突，同名可重建
* ``idx_target_project (project_id, is_deleted)``：列表/校验查询走索引

用 batch_alter_table 保证 SQLite（开发库）可回填表结构。

Revision ID: a3f6c8d21e47
Revises: 2f2753e09b0f
Create Date: 2026-10-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3f6c8d21e47"
down_revision: Union[str, None] = "2f2753e09b0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("execution_target", schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            "is_deleted", sa.Boolean(), server_default=sa.text("0"), nullable=False))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column(
            "deleted_seq", sa.BigInteger(), server_default=sa.text("0"), nullable=False))
        batch_op.create_index(
            "idx_target_project", ["project_id", "is_deleted"], unique=False)
        batch_op.create_unique_constraint(
            "uk_target_name", ["project_id", "name", "deleted_seq"])


def downgrade() -> None:
    with op.batch_alter_table("execution_target", schema=None) as batch_op:
        batch_op.drop_constraint("uk_target_name", type_="unique")
        batch_op.drop_index("idx_target_project")
        batch_op.drop_column("deleted_seq")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("is_deleted")
