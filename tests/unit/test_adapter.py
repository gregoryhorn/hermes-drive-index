from hermes_drive_index.hermes_adapter.tools import drive_index_search, drive_index_status, drive_index_update
import json


def test_adapter_handlers_return_json_for_validation_errors():
    payload = json.loads(drive_index_search(""))
    assert payload["success"] is False


def test_adapter_status_returns_json():
    payload = json.loads(drive_index_status())
    assert "success" in payload


def test_update_default_is_incremental_manifest(monkeypatch):
    calls = {}
    import hermes_drive_index.hermes_adapter.tools as tools

    def fake_incremental():
        calls["incremental"] = True
        return {"mode": "incremental_manifest"}

    monkeypatch.setattr(tools, "incremental_update", fake_incremental)
    payload = json.loads(drive_index_update())
    assert payload["success"] is True
    assert calls["incremental"] is True
    assert payload["requested_mode"] == "incremental_manifest"
