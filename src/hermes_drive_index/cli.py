"""Command-line interface for hermes-drive-index."""

from __future__ import annotations

import argparse
import json

from . import __version__
from .api import build_index, incremental_update, search, status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes Google Drive local index")
    parser.add_argument("--version", action="version", version=f"hermes-drive-index {__version__}")
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
    if args.cmd == "build":
        result = incremental_update() if args.mode in {"incremental", "incremental_manifest"} else build_index()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.cmd in {"update", "incremental"}:
        print(json.dumps(incremental_update(), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "status":
        print(json.dumps(status(), indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "doctor":
        import importlib.metadata as metadata
        eps = [str(e) for e in metadata.entry_points(group="hermes_agent.plugins") if "hermes_drive_index" in str(e)]
        print(json.dumps({"package": "hermes-drive-index", "version": __version__, "plugin_entry_points": eps, "status": status()}, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "search":
        result = search(args.query, args.top)
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
