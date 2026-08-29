"""Tests for the Alembic migration that renames ``documents.minio_key`` to ``s3_key``.

We exercise the migration against an ephemeral SQLite file:
  1. Set up a database that reflects the **pre-migration** state (table
     ``documents`` with a column literally named ``minio_key``, plus one row).
  2. Run ``alembic upgrade head`` and assert the column is renamed to
     ``s3_key`` and the row's data is preserved (rename must not lose data).
  3. Run ``alembic downgrade -1`` and assert the column is back to
     ``minio_key`` and the row's data is still preserved.

This guarantees the migration is reversible — and reversible migrations are
the contract Alembic exists to enforce.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATION_FILE_GLOB = "rename_minio_key_to_s3_key"


def _find_migration_file() -> Path:
    """Return the path of the rename migration script (or fail the test)."""
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    matches = sorted(versions_dir.glob(f"*_{MIGRATION_FILE_GLOB}.py"))
    if not matches:
        pytest.fail(
            f"No Alembic migration matching *_{MIGRATION_FILE_GLOB}.py "
            f"found in {versions_dir}"
        )
    return matches[0]


def _alembic(db_url: str, *args: str) -> subprocess.CompletedProcess:
    """Run ``alembic`` in a clean subprocess with the requested DB URL."""
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    return subprocess.run(
        ["alembic", *args],
        cwd=str(BACKEND_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture()
def temp_sqlite_url() -> str:
    """A throwaway SQLite file URL, cleaned up at the end of the test."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        db_path = tmp.name
    yield f"sqlite:///{db_path}"
    Path(db_path).unlink(missing_ok=True)


def _create_pre_migration_schema(db_url: str) -> None:
    """Create the ``documents`` table with the legacy ``minio_key`` column.

    This mirrors the state a database would be in **before** the s01b
    migration runs (i.e. the s01 schema, where the storage key column is
    still named ``minio_key``). We deliberately do NOT use the current
    SQLAlchemy model, which has already been renamed to ``s3_key``.
    """
    engine = create_engine(db_url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE documents (
                    id CHAR(36) NOT NULL PRIMARY KEY,
                    student_pseudo VARCHAR(64) NOT NULL,
                    subject VARCHAR(32) NOT NULL,
                    filename VARCHAR(512) NOT NULL,
                    minio_key VARCHAR(512) NOT NULL,
                    chunks_count INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(32) NOT NULL,
                    error_reason VARCHAR(1024),
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO documents (
                    id, student_pseudo, subject, filename,
                    minio_key, chunks_count, status, error_reason, created_at
                ) VALUES (
                    '11111111-1111-1111-1111-111111111111',
                    'ali', 'maths', 'cours.pdf',
                    'students/ali/11111111-1111-1111-1111-111111111111',
                    3, 'indexed', NULL, '2026-01-01 00:00:00'
                )
                """
            )
        )
    engine.dispose()


def _column_names(db_url: str, table: str) -> set[str]:
    engine = create_engine(db_url, future=True)
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    engine.dispose()
    return {row[1] for row in rows}


def _row(db_url: str) -> dict:
    engine = create_engine(db_url, future=True)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id, student_pseudo, filename FROM documents")
        ).fetchone()
    engine.dispose()
    assert result is not None, "documents row was lost by the migration"
    return {"id": result[0], "student_pseudo": result[1], "filename": result[2]}


class TestRenameMinioKeyMigration:
    def test_migration_script_exists(self) -> None:
        _find_migration_file()  # pytest.fail if missing

    def test_upgrade_renames_column_and_preserves_data(
        self, temp_sqlite_url: str
    ) -> None:
        _create_pre_migration_schema(temp_sqlite_url)
        assert "minio_key" in _column_names(temp_sqlite_url, "documents")

        result = _alembic(temp_sqlite_url, "upgrade", "head")
        assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"

        cols = _column_names(temp_sqlite_url, "documents")
        assert "s3_key" in cols
        assert "minio_key" not in cols
        # The row's identifying data is preserved.
        row = _row(temp_sqlite_url)
        assert row["id"] == "11111111-1111-1111-1111-111111111111"
        assert row["student_pseudo"] == "ali"
        assert row["filename"] == "cours.pdf"

    def test_downgrade_reverts_column_and_preserves_data(
        self, temp_sqlite_url: str
    ) -> None:
        _create_pre_migration_schema(temp_sqlite_url)
        upgrade = _alembic(temp_sqlite_url, "upgrade", "head")
        assert upgrade.returncode == 0, upgrade.stderr

        downgrade = _alembic(temp_sqlite_url, "downgrade", "-1")
        assert downgrade.returncode == 0, f"alembic downgrade failed:\n{downgrade.stderr}"

        cols = _column_names(temp_sqlite_url, "documents")
        assert "minio_key" in cols
        assert "s3_key" not in cols
        # The row's identifying data is preserved.
        row = _row(temp_sqlite_url)
        assert row["id"] == "11111111-1111-1111-1111-111111111111"
        assert row["student_pseudo"] == "ali"
