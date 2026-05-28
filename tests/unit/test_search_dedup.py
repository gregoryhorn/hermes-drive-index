from hermes_drive_index.api import search


def assert_unique_file_results(query: str, top_k: int = 5) -> None:
    result = search(query, top_k=top_k)
    rows = result["results"]
    file_ids = [row["file_id"] for row in rows]
    assert len(file_ids) == len(set(file_ids)), f"duplicate file_ids returned for {query!r}: {file_ids}"
    assert len(rows) <= top_k
    for row in rows:
        assert "chunks_matched" in row
        assert row["chunks_matched"] >= 1
        assert "extra_snippets" in row
        assert isinstance(row["extra_snippets"], list)


def test_search_dedup_live_local_index_regression():
    assert_unique_file_results("Fishing License Supporting Documents", top_k=5)
    assert_unique_file_results("Residential Lease Agreement Canal Residence West", top_k=5)
