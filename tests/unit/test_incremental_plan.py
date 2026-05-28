from hermes_drive_index.api import DriveFile, plan_incremental_actions


def df(file_id: str, *, name="Doc.pdf", path=None, modified="2026-01-01T00:00:00Z", md5="aaa", mime="application/pdf"):
    return DriveFile(
        id=file_id,
        name=name,
        mime_type=mime,
        path=path or f"Personal Files/{name}",
        size=123,
        modified_time=modified,
        md5_checksum=md5,
        web_view_link=f"https://example.invalid/{file_id}",
    )


def test_incremental_plan_regression():
    current = {
        "unchanged": {"file_id": "unchanged", "name": "Doc.pdf", "path": "Personal Files/Doc.pdf", "mime_type": "application/pdf", "modified_time": "2026-01-01T00:00:00Z", "md5_checksum": "aaa", "status": "indexed", "web_view_link": "https://example.invalid/unchanged"},
        "renamed": {"file_id": "renamed", "name": "Old.pdf", "path": "Personal Files/Old.pdf", "mime_type": "application/pdf", "modified_time": "2026-01-01T00:00:00Z", "md5_checksum": "bbb", "status": "indexed", "web_view_link": "https://example.invalid/renamed"},
        "changed": {"file_id": "changed", "name": "Changed.pdf", "path": "Personal Files/Changed.pdf", "mime_type": "application/pdf", "modified_time": "2026-01-01T00:00:00Z", "md5_checksum": "old", "status": "indexed", "web_view_link": "https://example.invalid/changed"},
        "deleted": {"file_id": "deleted", "name": "Deleted.pdf", "path": "Personal Files/Deleted.pdf", "mime_type": "application/pdf", "modified_time": "2026-01-01T00:00:00Z", "md5_checksum": "gone", "status": "indexed", "web_view_link": "https://example.invalid/deleted"},
    }
    crawled = [
        df("unchanged", md5="aaa"),
        df("renamed", name="New.pdf", path="Personal Files/Renamed/New.pdf", md5="bbb"),
        df("changed", name="Changed.pdf", md5="new"),
        df("new", name="New File.pdf", md5="ccc"),
        df("skip-photo", name="Photo.jpg", mime="image/jpeg"),
    ]
    plan = plan_incremental_actions(crawled, current)
    assert plan["unchanged"] == ["unchanged"]
    assert plan["metadata_only"] == ["renamed"]
    assert plan["reindex"] == ["changed", "new"]
    assert plan["delete"] == ["deleted"]
    assert plan["skip"] == ["skip-photo"]
