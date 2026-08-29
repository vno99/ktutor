"""rename_minio_key_to_s3_key

Story s01b — migrate the storage backend from MinIO to SeaweedFS. The
``documents.minio_key`` column is renamed to ``documents.s3_key`` to match
the new naming. The column is renamed (not dropped/recreated) so existing
data is preserved.

Revision ID: f6211a490dce
Revises:
Create Date: 2026-08-29 11:04:26.612089

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6211a490dce"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename ``documents.minio_key`` to ``documents.s3_key``."""
    op.alter_column("documents", "minio_key", new_column_name="s3_key")


def downgrade() -> None:
    """Reverse the rename: ``documents.s3_key`` back to ``documents.minio_key``."""
    op.alter_column("documents", "s3_key", new_column_name="minio_key")
