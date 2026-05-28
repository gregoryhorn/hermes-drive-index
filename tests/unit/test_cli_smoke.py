"""Offline CLI smoke tests (Phase E-8)."""

from __future__ import annotations

import json

import pytest

from hermes_drive_index import cli


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "hermes-drive-index" in capsys.readouterr().out


def test_status_reports_missing_db(tmp_path, monkeypatch, capsys):
    db = tmp_path / "nope.db"
    monkeypatch.setenv("HERMES_DRIVE_INDEX_DB_PATH", str(db))
    assert cli.main(["status"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["exists"] is False


def test_doctor_reports_status_and_entry_points(tmp_path, monkeypatch, capsys):
    db = tmp_path / "nope.db"
    monkeypatch.setenv("HERMES_DRIVE_INDEX_DB_PATH", str(db))
    assert cli.main(["doctor"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["package"] == "hermes-drive-index"
    assert payload["status"]["exists"] is False
