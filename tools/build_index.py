"""Build a single registry.json index from all YAML entries."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


ROOT = Path(__file__).parent.parent
DATA_DIRS = [ROOT / "data" / "pypi", ROOT / "data" / "npm"]
OUTPUT_PATH = ROOT / "generated" / "registry.json"


def build_index() -> dict:
    """Build a single JSON index from all YAML entries."""
    entries = []

    for data_dir in DATA_DIRS:
        if not data_dir.exists():
            continue

        for yaml_file in sorted(data_dir.glob("*.yaml")):
            with open(yaml_file) as f:
                file_entries = list(yaml.safe_load_all(f))

            for entry in file_entries:
                if entry is None:
                    continue
                # Add source file metadata
                entry["_source_file"] = str(yaml_file.relative_to(ROOT))
                entries.append(entry)

    index = {
        "version": "1.0.0",
        "generated_at": date.today().isoformat(),
        "total_entries": len(entries),
        "entries": entries,
    }

    return index


def main():
    index = build_index()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(index, f, indent=2)

    print(f"Generated {OUTPUT_PATH.relative_to(ROOT)} with {index['total_entries']} entries")

    # Also print a summary
    by_ecosystem = {}
    for entry in index["entries"]:
        eco = entry.get("ecosystem", "?")
        by_ecosystem[eco] = by_ecosystem.get(eco, 0) + 1

    print("\nSummary:")
    for eco, count in sorted(by_ecosystem.items()):
        print(f"  {eco}: {count} entries")

    # List all entries
    print("\nEntries:")
    for entry in index["entries"]:
        pkg = entry.get("package", "?")
        eco = entry.get("ecosystem", "?")
        from_v = entry.get("from_version_range", "?")
        to_v = entry.get("to_version_range", "?")
        print(f"  {pkg} ({eco}): {from_v} -> {to_v}")


if __name__ == "__main__":
    main()
