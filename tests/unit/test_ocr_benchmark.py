"""Read-only aggregate OCR benchmark tests."""

from __future__ import annotations

import json
import sqlite3

from hermes_drive_index import cli
from hermes_drive_index.config import DriveIndexConfig
from hermes_drive_index.core import benchmark as benchmark_mod
from hermes_drive_index.core.benchmark import benchmark_ocr_parameters
from hermes_drive_index.core.index import init_db
from hermes_drive_index.core.models import DriveFile


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


def drive_file(file_id: str, name: str = "PRIVATE_SCAN_123.pdf") -> DriveFile:
    return DriveFile(
        id=file_id,
        name=name,
        mime_type="application/pdf",
        path=f"Personal Files/Private Folder/{name}",
        size=123,
        modified_time="2026-01-01T00:00:00Z",
        md5_checksum="abc",
        web_view_link=f"https://drive.example/{file_id}",
    )


def seed_file(con: sqlite3.Connection, f: DriveFile, status: str, text: str | None = None) -> None:
    con.execute(
        "insert or replace into files values (?,?,?,?,?,?,?,?,?,?,?)",
        (f.id, f.name, f.path, f.mime_type, f.size, f.modified_time, f.md5_checksum, f.web_view_link, None, status, None),
    )
    if text:
        cur = con.execute(
            "insert into chunks(chunk_id,file_id,chunk_index,text,token_estimate) values (?,?,?,?,?)",
            (f"chunk-{f.id}", f.id, 0, text, 1),
        )
        con.execute(
            "insert into chunks_fts(rowid,text,name,path,file_id,chunk_id) values (?,?,?,?,?,?)",
            (cur.lastrowid, text, f.name, f.path, f.id, f"chunk-{f.id}"),
        )


def test_benchmark_ocr_parameters_returns_aggregate_only(tmp_path, monkeypatch):
    c = cfg(tmp_path)
    c.cache_dir.mkdir(parents=True)
    con = init_db(c.db_path)
    private = drive_file("PRIVATE_DRIVE_ID", "PRIVATE_FILENAME_123.pdf")
    seed_file(con, private, "indexed_metadata", text="PRIVATE_FILENAME_123.pdf metadata only")
    con.commit(); con.close()

    golden = tmp_path / "golden.json"
    golden.write_text(json.dumps([{"query": "secretneedle", "expected_path_contains": "Private Folder/PRIVATE_FILENAME_123.pdf"}]))

    monkeypatch.setattr(benchmark_mod, "build_drive_service", lambda _path: object())
    monkeypatch.setattr(benchmark_mod, "crawl", lambda *_args: [private])

    def fake_index_file(con, _service, _cache_dir, f, metrics, **kwargs):
        assert kwargs["ocr_pdf_enabled"] is True
        assert kwargs["ocr_pdf_args"] == ()
        metrics["bytes_downloaded"] += 42
        metrics["files_indexed_ocr"] += 1
        con.execute("delete from chunks_fts where file_id=?", (f.id,))
        con.execute("delete from chunks where file_id=?", (f.id,))
        con.execute("update files set status='indexed_ocr', error=null where file_id=?", (f.id,))
        cur = con.execute(
            "insert into chunks(chunk_id,file_id,chunk_index,text,token_estimate) values (?,?,?,?,?)",
            ("ocr-chunk", f.id, 0, "secretneedle", 3),
        )
        con.execute(
            "insert into chunks_fts(rowid,text,name,path,file_id,chunk_id) values (?,?,?,?,?,?)",
            (cur.lastrowid, "secretneedle", f.name, f.path, f.id, "ocr-chunk"),
        )
        metrics["chunks"] += 1

    monkeypatch.setattr(benchmark_mod, "index_file", fake_index_file)

    result = benchmark_ocr_parameters(c, modes=["ocr_default"], golden_path=golden)

    assert result["read_only"] is True
    assert result["candidate_count"] == 1
    assert result["before_status_counts"]["indexed_metadata"] == 1
    mode = result["modes"][0]
    assert mode["bytes_downloaded"] == 42
    assert mode["files_failed"] == 0
    assert mode["conversions"]["to_indexed_ocr"] == 1
    assert mode["conversions"]["remaining_indexed_metadata"] == 0
    assert result["evaluation_baseline"]["recall_at_5"] == 0.0
    assert mode["evaluation"]["recall_at_5"] == 1.0
    assert mode["evaluation_delta"]["recall_at_5"] == 1.0

    payload = json.dumps(result)
    assert "PRIVATE_DRIVE_ID" not in payload
    assert "PRIVATE_FILENAME_123" not in payload
    assert "Private Folder" not in payload
    assert "secretneedle" not in payload

    original = sqlite3.connect(c.db_path)
    status = original.execute("select status from files where file_id=?", (private.id,)).fetchone()[0]
    original.close()
    assert status == "indexed_metadata"


def test_benchmark_mode_selection_passes_nondefault_args(tmp_path, monkeypatch):
    c = cfg(tmp_path)
    con = init_db(c.db_path)
    private = drive_file("id-2")
    seed_file(con, private, "indexed_metadata", text="metadata")
    con.commit(); con.close()
    monkeypatch.setattr(benchmark_mod, "build_drive_service", lambda _path: object())
    monkeypatch.setattr(benchmark_mod, "crawl", lambda *_args: [private])
    seen_args = []

    def fake_index_file(con, _service, _cache_dir, f, metrics, **kwargs):
        seen_args.append(kwargs["ocr_pdf_args"])
        con.execute("update files set status='indexed_metadata' where file_id=?", (f.id,))

    monkeypatch.setattr(benchmark_mod, "index_file", fake_index_file)

    result = benchmark_ocr_parameters(c, modes=["rotate_deskew"])

    assert seen_args == [("--rotate-pages", "--deskew")]
    assert result["modes"][0]["mode"] == "rotate_deskew"


def test_cli_routes_benchmark_ocr(tmp_path, monkeypatch, capsys):
    def fake_benchmark(cfg, **kwargs):
        assert kwargs["modes"] == ["ocr_default"]
        assert kwargs["limit"] == 1
        return {"mode": "ocr_parameter_benchmark_read_only", "read_only": True}

    monkeypatch.setattr(cli, "benchmark_ocr_parameters", fake_benchmark)

    assert cli.main(["benchmark-ocr", "--mode", "ocr_default", "--limit", "1", "--json"]) == 0
    out = capsys.readouterr().out
    assert '"read_only": true' in out
