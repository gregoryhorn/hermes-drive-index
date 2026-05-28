from hermes_drive_index.core.index import init_db
from hermes_drive_index.core.search import search_db


def _make_search_fixture(tmp_path):
    db_path = tmp_path / "index.db"
    con = init_db(db_path)
    files = [
        ("file-a", "Alpha Plan.pdf", "Drive/Alpha Plan.pdf", "application/pdf", 123, "2026-01-01T00:00:00Z", None, "https://example.com/a", "2026-01-01T00:00:00Z", "indexed", None),
        ("file-b", "Beta Plan.pdf", "Drive/Beta Plan.pdf", "application/pdf", 456, "2026-01-01T00:00:00Z", None, "https://example.com/b", "2026-01-01T00:00:00Z", "indexed", None),
    ]
    con.executemany("insert into files values (?,?,?,?,?,?,?,?,?,?,?)", files)
    chunks = [
        ("a-0", "file-a", 0, "alpha project plan budget timeline", 8),
        ("a-1", "file-a", 1, "alpha project plan milestones owners", 8),
        ("a-2", "file-a", 2, "alpha project plan risk register", 8),
        ("b-0", "file-b", 0, "beta project plan budget", 8),
    ]
    for chunk_id, file_id, idx, text, tokens in chunks:
        cur = con.execute(
            "insert into chunks(chunk_id,file_id,chunk_index,text,token_estimate) values (?,?,?,?,?)",
            (chunk_id, file_id, idx, text, tokens),
        )
        file_row = con.execute("select name,path from files where file_id=?", (file_id,)).fetchone()
        con.execute(
            "insert into chunks_fts(rowid,text,name,path,file_id,chunk_id) values (?,?,?,?,?,?)",
            (cur.lastrowid, text, file_row[0], file_row[1], file_id, chunk_id),
        )
    con.commit()
    con.close()
    return db_path


def test_search_results_are_deduped_by_file(tmp_path):
    result = search_db(_make_search_fixture(tmp_path), "project plan", top_k=5)
    rows = result["results"]
    by_file = {row["file_id"]: row for row in rows}

    assert set(by_file) == {"file-a", "file-b"}
    assert len(rows) == len(by_file)
    assert result["deduped_by_file"] is True
    assert result["raw_candidates"] == 4
    assert by_file["file-a"]["chunks_matched"] == 3
    assert len(by_file["file-a"]["extra_snippets"]) == 2
    assert by_file["file-b"]["chunks_matched"] == 1
    assert by_file["file-b"]["extra_snippets"] == []


def test_search_respects_top_k_after_dedup(tmp_path):
    result = search_db(_make_search_fixture(tmp_path), "project plan", top_k=1)
    assert len(result["results"]) == 1
    assert result["results"][0]["file_id"] in {"file-a", "file-b"}
