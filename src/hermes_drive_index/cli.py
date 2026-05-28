"""Command-line interface for hermes-drive-index."""

from __future__ import annotations

import argparse
import json

from . import __version__
from .api import build_index, incremental_update, search, status
from .config import load_config


def _config_from_args(args: argparse.Namespace):
    return load_config(
        {
            "config_path": args.config,
            "root_folder_id": args.root_folder_id,
            "db_path": args.db_path,
            "base_dir": args.base_dir,
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes Google Drive local index")
    parser.add_argument("--version", action="version", version=f"hermes-drive-index {__version__}")
    parser.add_argument("--config", help="Path to a local TOML config file.")
    parser.add_argument("--root-folder-id", dest="root_folder_id", help="Drive root folder ID override.")
    parser.add_argument("--db-path", dest="db_path", help="Index DB path override.")
    parser.add_argument("--base-dir", dest="base_dir", help="Base directory override.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    build_p = sub.add_parser("build")
    build_p.add_argument("--mode", choices=["weekly_full", "full", "incremental", "incremental_manifest"], default="weekly_full")

    update_p = sub.add_parser("update")
    update_p.add_argument("--mode", choices=["incremental", "incremental_manifest"], default="incremental_manifest")
    sub.add_parser("incremental")
    sub.add_parser("status")
    sub.add_parser("doctor")

    sp = sub.add_parser("search")
    sp.add_argument("query")
    sp.add_argument("--top", type=int, default=8)
    sp.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    cfg = _config_from_args(args)
    if args.cmd == "build":
        result = incremental_update(cfg) if args.mode in {"incremental", "incremental_manifest"} else build_index(cfg)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.cmd in {"update", "incremental"}:
        print(json.dumps(incremental_update(cfg), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "status":
        print(json.dumps(status(cfg), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "doctor":
        import importlib.metadata as metadata
        eps = [str(e) for e in metadata.entry_points(group="hermes_agent.plugins") if "hermes_drive_index" in str(e)]
        print(json.dumps({"package": "hermes-drive-index", "version": __version__, "plugin_entry_points": eps, "status": status(cfg)}, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "search":
        result = search(args.query, args.top, cfg)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Query: {result['query']} ({result['latency_ms']} ms)")
            for i, row in enumerate(result["results"], 1):
                print(f"\n{i}. {row['name']}\n   {row['path']}\n   {row.get('web_view_link')}\n   {row['snippet']}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
