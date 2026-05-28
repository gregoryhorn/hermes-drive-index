"""SQLite index management."""

from __future__ import annotations

from pathlib import Path
import hashlib
import sqlite3
from typing import Any

from .crawler import download_or_export
from .extract import chunk_text, extract_text
from .models import DriveFile
from .utils import now_iso

#: Current on-disk index schema version. Bumped only when the schema changes.
SCHEMA_VERSION = "1"


def init_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(
        """
        pragma journal_mode=WAL;
        create table meta(key text primary key, value text);
        create table files(
          file_id text primary key,
          name text,
          path text,
          mime_type text,
          size_bytes integer,
          modified_time text,
          md5_checksum text,
          web_view_link text,
          indexed_at text,
          status text,
          error text
        );
        create table chunks(
          id integer primary key autoincrement,
          chunk_id text unique,
          file_id text,
          chunk_index integer,
          text text,
          token_estimate integer,
          foreign key(file_id) references files(file_id)
        );
        create virtual table chunks_fts using fts5(
          text,
          name,
          path,
          file_id unindexed,
          chunk_id unindexed
        );
        create table runs(
          run_id text primary key,
          started_at text,
          finished_at text,
          mode text,
          files_scanned integer,
          files_indexed integer,
          files_skipped integer,
          files_failed integer,
          bytes_downloaded integer,
          chunks integer,
          status text
        );
        """
    )
    con.execute("insert or replace into meta(key, value) values ('schema_version', ?)", (SCHEMA_VERSION,))
    con.commit()
    return con


def read_schema_version(con: sqlite3.Connection) -> str | None:
    """Return the stored schema version, or ``None`` for legacy/pre-meta DBs.

    A missing ``meta`` table (older indexes built before this column existed) is
    treated as the legacy sentinel ``None``, which callers handle as "v1".
    """
    try:
        row = con.execute("select value from meta where key='schema_version'").fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    return row[0] if not isinstance(row, sqlite3.Row) else row["value"]


def migrate(con: sqlite3.Connection) -> None:
    """No-op migration hook.

    Current and legacy (``None``) versions need no migration. An unrecognized
    future version raises so we never silently operate on an incompatible DB.
    """
    version = read_schema_version(con)
    if version in (None, SCHEMA_VERSION):
        return
    raise RuntimeError(f"Unknown index schema version {version!r}; upgrade hermes-drive-index to open this DB.")


def insert_skipped_file(con: sqlite3.Connection, f: DriveFile) -> None:
    con.execute(
        "insert or replace into files values (?,?,?,?,?,?,?,?,?,?,?)",
        (f.id, f.name, f.path, f.mime_type, f.size, f.modified_time, f.md5_checksum, f.web_view_link, None, "skipped", None),
    )


def delete_file_from_index(con: sqlite3.Connection, file_id: str) -> None:
    con.execute("delete from chunks_fts where rowid in (select id from chunks where file_id=?)", (file_id,))
    con.execute("delete from chunks where file_id=?", (file_id,))
    con.execute("delete from files where file_id=?", (file_id,))


def reinsert_fts_for_file(con: sqlite3.Connection, f: DriveFile) -> int:
    rows = con.execute("select id, chunk_id, text from chunks where file_id=? order by chunk_index", (f.id,)).fetchall()
    con.execute("delete from chunks_fts where rowid in (select id from chunks where file_id=?)", (f.id,))
    for row in rows:
        con.execute("insert into chunks_fts(rowid,text,name,path,file_id,chunk_id) values (?,?,?,?,?,?)", (row["id"], row["text"], f.name, f.path, f.id, row["chunk_id"]))
    return len(rows)


def update_file_metadata(con: sqlite3.Connection, f: DriveFile, existing: dict) -> int:
    con.execute(
        "update files set name=?, path=?, mime_type=?, size_bytes=?, modified_time=?, md5_checksum=?, web_view_link=? where file_id=?",
        (f.name, f.path, f.mime_type, f.size, f.modified_time, f.md5_checksum, f.web_view_link, f.id),
    )
    if existing.get("name") != f.name or existing.get("path") != f.path:
        return reinsert_fts_for_file(con, f)
    return 0


def index_file(con: sqlite3.Connection, service: Any, cache_dir: Path, f: DriveFile, metrics: dict) -> None:
    delete_file_from_index(con, f.id)
    local = download_or_export(service, cache_dir, f)
    metrics["bytes_downloaded"] += local.stat().st_size if local and local.exists() else 0
    text = extract_text(local, f) if local else ""
    chunks = chunk_text(text) if text.strip() else []
    error = None
    if not chunks:
        status = "indexed_metadata"
        error = "no text extracted; indexed filename/path metadata only"
        chunks = [f"{f.name}\n{f.path}\n{f.mime_type}"]
    else:
        status = "indexed"
    con.execute(
        "insert or replace into files values (?,?,?,?,?,?,?,?,?,?,?)",
        (f.id, f.name, f.path, f.mime_type, f.size, f.modified_time, f.md5_checksum, f.web_view_link, now_iso(), status, error),
    )
    for i, ch in enumerate(chunks):
        chunk_id = hashlib.sha1(f"{f.id}:{i}".encode()).hexdigest()
        cur = con.execute("insert into chunks(chunk_id,file_id,chunk_index,text,token_estimate) values (?,?,?,?,?)", (chunk_id, f.id, i, ch, max(1, len(ch) // 4)))
        con.execute("insert into chunks_fts(rowid,text,name,path,file_id,chunk_id) values (?,?,?,?,?,?)", (cur.lastrowid, ch, f.name, f.path, f.id, chunk_id))
        metrics["chunks"] += 1


def existing_files(con: sqlite3.Connection) -> dict[str, dict]:
    return {r["file_id"]: dict(r) for r in con.execute("select * from files")}
