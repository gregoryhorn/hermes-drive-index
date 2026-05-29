"""Metadata-only reindex mode tests."""

from __future__ import annotations

import sqlite3

from hermes_drive_index.config import DriveIndexConfig
from hermes_drive_index.core.index import init_db
from hermes_drive_index.core.models import DriveFile
from hermes_drive_index.core import orchestrator as orchestrator_mod
from hermes_drive_index.core.orchestrator import reindex_metadata_only
from hermes_drive_index import cli
from hermes_drive_index.hermes_adapter import tools


def cfg(tmp_path) -> DriveIndexConfig:
    return DriveIndexConfig(
        root_folder_id="root",
        root_folder_name="Personal Files",
        base_dir=tmp_path,
        cache_dir=tmp_path / "cache",
        db_path=tmp_path / "index.db",
        google_api_dir=tmp_path / "google",
        config_path=tmp_path / "config.toml",
        ocr_enabled=True,
        ocr_image_enabled=False,
    )


def drive_file(file_id: str, name: str = "scan.pdf") -> DriveFile:
    return DriveFile(
        id=file_id,
        name=name,
        mime_type="application/pdf",
        path=f"Personal Files/{name}",
        size=123,
        modified_time="2026-01-01T00:00:00Z",
        md5_checksum="abc",
        web_view_link=f"https://example.invalid/{file_id}",
    )


def seed_file(con: sqlite3.Connection, f: DriveFile, status: str) -> None:
    con.execute(
        "insert or replace into files values (?,?,?,?,?,?,?,?,?,?,?)",
        (f.id, f.name, f.path, f.mime_type, f.size, f.modified_time, f.md5_checksum, f.web_view_link, None, status, None),
    )


def test_reindex_metadata_only_reindexes_only_metadata_rows(tmp_path, monkeypatch):
    c = cfg(tmp_path)
    c.cache_dir.mkdir(parents=True)
    con = init_db(c.db_path)
    meta = drive_file("meta", "scan.pdf")
    indexed = drive_file("indexed", "native.pdf")
    skipped = drive_file("skipped", "photo.pdf")
    seed_file(con, meta, "indexed_metadata")
    seed_file(con, indexed, "indexed")
    seed_file(con, skipped, "skipped")
    con.commit(); con.close()
    calls: list[str] = []

    monkeypatch.setattr(orchestrator_mod, "build_drive_service", lambda _path: object())
    monkeypatch.setattr(orchestrator_mod, "crawl", lambda *_args: [meta, indexed, skipped])

    def fake_index_file(_con, _service, _cache_dir, f, metrics, **kwargs):
        calls.append(f.id)
        metrics["files_indexed_ocr"] += 1
        metrics["chunks"] += 1
        _con.execute(
            "update files set status='indexed_ocr', indexed_at='now', error=null where file_id=?",
            (f.id,),
        )

    monkeypatch.setattr(orchestrator_mod, "index_file", fake_index_file)

    result = reindex_metadata_only(c)

    assert calls == ["meta"]
    assert result["mode"] == "reindex_metadata_only"
    assert result["files_considered"] == 1
    assert result["files_reindexed"] == 1
    assert result["files_failed"] == 0


def test_reindex_metadata_only_deletes_missing_metadata_rows(tmp_path, monkeypatch):
    c = cfg(tmp_path)
    c.cache_dir.mkdir(parents=True)
    con = init_db(c.db_path)
    missing = drive_file("missing", "missing.pdf")
    seed_file(con, missing, "indexed_metadata")
    con.commit(); con.close()

    monkeypatch.setattr(orchestrator_mod, "build_drive_service", lambda _path: object())
    monkeypatch.setattr(orchestrator_mod, "crawl", lambda *_args: [])

    result = reindex_metadata_only(c)

    con = sqlite3.connect(c.db_path)
    count = con.execute("select count(*) from files where file_id='missing'").fetchone()[0]
    con.close()
    assert count == 0
    assert result["files_deleted"] == 1
    assert result["files_reindexed"] == 0


def test_cli_accepts_reindex_metadata_only_mode(tmp_path, monkeypatch, capsys):
    def fake_reindex(cfg):
        assert cfg.ocr_enabled is True
        return {"mode": "reindex_metadata_only", "files_reindexed": 0}

    monkeypatch.setattr(cli, "reindex_metadata_only", fake_reindex)

    assert cli.main(["--ocr", "update", "--mode", "reindex_metadata_only", "--json"]) == 0
    assert '"mode": "reindex_metadata_only"' in capsys.readouterr().out


def test_adapter_routes_reindex_metadata_only_mode(monkeypatch):
    monkeypatch.setattr(tools, "reindex_metadata_only", lambda: {"mode": "reindex_metadata_only"})

    payload = tools.json.loads(tools.drive_index_update("reindex_metadata_only"))

    assert payload["success"] is True
    assert payload["mode"] == "reindex_metadata_only"
