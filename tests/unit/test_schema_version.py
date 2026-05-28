"""Index schema version / meta table (Phase E-5)."""

from __future__ import annotations

import sqlite3

import pytest

from hermes_drive_index.core.index import SCHEMA_VERSION, init_db, migrate, read_schema_version


def test_fresh_db_reports_current_version(tmp_path):
    con = init_db(tmp_path / "index.new.db")
    assert read_schema_version(con) == SCHEMA_VERSION == "1"
    migrate(con)  # no-op on current
    con.close()


def test_legacy_db_without_meta_table_opens_cleanly(tmp_path):
    path = tmp_path / "legacy.db"
    con = sqlite3.connect(path)
    con.execute("create table files(file_id text primary key)")
    con.commit()
    assert read_schema_version(con) is None
    migrate(con)  # legacy sentinel needs no migration
    con.close()


def test_unknown_future_version_raises(tmp_path):
    con = init_db(tmp_path / "index.new.db")
    con.execute("update meta set value='999' where key='schema_version'")
    con.commit()
    with pytest.raises(RuntimeError):
        migrate(con)
    con.close()
