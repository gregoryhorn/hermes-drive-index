"""Search and status over the SQLite FTS index."""

from __future__ import annotations

from pathlib import Path
import re
import sqlite3
import time


def search_db(db_path: Path, query: str, top_k: int = 8) -> dict:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    start = time.time()
    q = " ".join(re.findall(r"[\w]+", query)) or query
    raw_limit = max(top_k * 6, top_k)
    rows = con.execute(
        """
        select bm25(chunks_fts) as score, snippet(chunks_fts, 0, '[', ']', ' … ', 20) as snippet,
               chunks_fts.file_id, chunks_fts.chunk_id, chunks_fts.name, chunks_fts.path,
               files.web_view_link, files.modified_time, files.mime_type
        from chunks_fts join files on files.file_id = chunks_fts.file_id
        where chunks_fts match ?
        order by score limit ?
        """,
        (q, raw_limit),
    ).fetchall()

    grouped: dict[str, dict] = {}
    for row in rows:
        item = dict(row)
        file_id = item["file_id"]
        if file_id not in grouped:
            item["chunks_matched"] = 1
            item["extra_snippets"] = []
            grouped[file_id] = item
            continue

        grouped[file_id]["chunks_matched"] += 1
        snippet = item.get("snippet")
        extras = grouped[file_id]["extra_snippets"]
        if snippet and snippet != grouped[file_id].get("snippet") and snippet not in extras and len(extras) < 2:
            extras.append(snippet)

    results = list(grouped.values())[:top_k]
    elapsed = time.time() - start
    return {
        "query": query,
        "fts_query": q,
        "latency_ms": round(elapsed * 1000, 2),
        "results": results,
        "deduped_by_file": True,
        "raw_candidates": len(rows),
    }


def status_db(db_path: Path) -> dict:
    if not db_path.exists():
        return {"exists": False, "path": str(db_path)}
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    counts = dict(con.execute("select status, count(*) c from files group by status").fetchall())
    last = con.execute("select * from runs order by started_at desc limit 1").fetchone()
    return {"exists": True, "path": str(db_path), "db_bytes": db_path.stat().st_size, "counts": counts, "last_run": dict(last) if last else None}
