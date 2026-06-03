from __future__ import annotations

from hermes_drive_index.config import load_config
from hermes_drive_index.core.models import DriveFile
from hermes_drive_index.core.organize import OrganizeConfig, OrganizeRule, drive_query_string, plan_organize_file


def sample_file(**kw) -> DriveFile:
    data = {
        "id": "file-1",
        "name": "scan_001.pdf",
        "mime_type": "application/pdf",
        "path": "Personal Files/Inbox/scan_001.pdf",
        "size": 123,
        "modified_time": "2026-06-03T12:00:00Z",
        "md5_checksum": "abc",
        "web_view_link": "https://drive.google.com/file/d/file-1/view",
        "parents": ("inbox-id",),
    }
    data.update(kw)
    return DriveFile(**data)


def test_auto_organize_disabled_by_default_plans_nothing():
    assert plan_organize_file(sample_file(), OrganizeConfig()) is None


def test_auto_organize_default_target_renders_standard_name():
    action = plan_organize_file(
        sample_file(name="messy_scan-name.pdf"),
        OrganizeConfig(enabled=True, default_target_folder_path="Personal Files/Documents/Unsorted"),
    )
    assert action is not None
    assert action["dry_run"] is True
    assert action["target_folder_path"] == "Personal Files/Documents/Unsorted"
    assert action["new_name"] == "2026-06-03 - Unsorted - messy scan name.pdf"
    assert action["needs_move"] is True
    assert action["needs_rename"] is True


def test_auto_organize_rule_overrides_target_category_and_template():
    cfg = OrganizeConfig(
        enabled=True,
        default_target_folder_path="Personal Files/Documents/Unsorted",
        rules=(
            OrganizeRule(
                name="invoice",
                pattern=r"invoice|receipt",
                target_folder_path="Personal Files/Finance/Receipts",
                category="Receipt",
                rename_template="{date} - {category} - {title}{ext}",
            ),
        ),
    )
    action = plan_organize_file(sample_file(name="amazon receipt.pdf"), cfg)
    assert action is not None
    assert action["rule"] == "invoice"
    assert action["target_folder_path"] == "Personal Files/Finance/Receipts"
    assert action["new_name"] == "2026-06-03 - Receipt - amazon receipt.pdf"


def test_auto_organize_config_from_toml(tmp_path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '''
root_folder_id = "root"
google_api_dir = "/tmp/google-api"

[auto_organize]
enabled = true
dry_run = false
default_target_folder_path = "Personal Files/Documents/Unsorted"
rename_template = "{date} - {category} - {title}{ext}"

[[auto_organize.rules]]
name = "receipts"
pattern = "receipt|invoice"
target_folder_path = "Personal Files/Finance/Receipts"
category = "Receipt"
'''
    )
    cfg = load_config({"config_path": str(config_path), "base_dir": str(tmp_path)})
    assert cfg.auto_organize.enabled is True
    assert cfg.auto_organize.dry_run is False
    assert cfg.auto_organize.default_target_folder_path == "Personal Files/Documents/Unsorted"
    assert len(cfg.auto_organize.rules) == 1
    assert cfg.auto_organize.rules[0].name == "receipts"


def test_drive_query_string_escapes_single_quotes_and_backslashes():
    assert drive_query_string("Gregory's Docs\\Archive") == "Gregory\\'s Docs\\\\Archive"
