#!/usr/bin/env python3
"""Build generated/registry.json from source YAML files.

Usage:
    python scripts/build_registry.py          # rebuild registry.json
    python scripts/build_registry.py --check  # fail if committed JSON is stale
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_PYPI = ROOT / "data" / "pypi"
DATA_NPM = ROOT / "data" / "npm"
OUTPUT = ROOT / "generated" / "registry.json"


def build_registry() -> dict:
    """Rebuild the registry dict from all YAML source files."""
    entries: list[dict] = []

    for ecosystem_dir in [DATA_PYPI, DATA_NPM]:
        if not ecosystem_dir.exists():
            continue
        for yaml_file in sorted(ecosystem_dir.glob("*.yaml")):
            with open(yaml_file) as f:
                pkg = yaml.safe_load(f)
            if pkg is None:
                print(f"WARNING: {yaml_file} is empty", file=sys.stderr)
                continue
            entry = {
                "package": pkg["package"],
                "ecosystem": pkg["ecosystem"],
                "from_version_range": pkg.get("from_version_range", ""),
                "to_version_range": pkg.get("to_version_range", ""),
                "severity": pkg.get("severity", "medium"),
                "category": pkg.get("category", "api_break"),
                "summary": pkg.get("summary", ""),
                "changes": pkg.get("changes", []),
                "sources": pkg.get("sources", []),
                "last_verified": pkg.get("last_verified", ""),
                "confidence": pkg.get("confidence", ""),
            }
            entries.append(entry)

    total = sum(len(e["changes"]) for e in entries)
    registry = {
        "version": "1.0",
        "total_changes": total,
        "packages": sorted(list(set(e["package"] for e in entries))),
        "entries": entries,
    }
    return registry


def write_registry(path: pathlib.Path | None = None) -> dict:
    """Build and write registry.json. Returns the registry dict."""
    registry = build_registry()
    out = path or OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(registry, f, indent=2)
    return registry


def check_stale() -> int:
    """Rebuild to a temp file and compare against committed registry.json.

    Returns 0 if they match, 1 if the committed file is stale.
    """
    if not OUTPUT.exists():
        print(f"ERROR: {OUTPUT} does not exist. Run build first.", file=sys.stderr)
        return 1

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        registry = build_registry()
        json.dump(registry, tmp, indent=2)
        tmp_path = pathlib.Path(tmp.name)

    committed = json.loads(OUTPUT.read_text())
    fresh = json.loads(tmp_path.read_text())

    tmp_path.unlink(missing_ok=True)

    if committed == fresh:
        print(f"OK: {OUTPUT} is up to date ({registry['total_changes']} changes)")
        return 0
    else:
        print(f"STALE: {OUTPUT} does not match YAML sources.", file=sys.stderr)
        committed_count = committed.get("total_changes", "?")
        fresh_count = fresh.get("total_changes", "?")
        if committed_count != fresh_count:
            print(
                f"  Change count: committed={committed_count}, fresh={fresh_count}",
                file=sys.stderr,
            )
        return 1


def main():
    if "--check" in sys.argv:
        sys.exit(check_stale())

    registry = write_registry()
    print(f"Built {OUTPUT}")
    print(f"  Packages: {len(registry['entries'])}")
    print(f"  Total changes: {registry['total_changes']}")
    for e in registry["entries"]:
        print(f"  {e['package']} ({e['ecosystem']}): {len(e['changes'])} changes")


if __name__ == "__main__":
    main()
