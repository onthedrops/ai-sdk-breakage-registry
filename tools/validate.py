"""Validate all YAML breaking-change entries against the JSON schema."""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    from jsonschema import validate, ValidationError
except ImportError:
    print("jsonschema not installed. Run: pip install jsonschema", file=sys.stderr)
    sys.exit(1)


ROOT = Path(__file__).parent.parent
SCHEMA_PATH = ROOT / "schema" / "breaking-change.schema.json"
DATA_DIRS = [ROOT / "data" / "pypi", ROOT / "data" / "npm"]


def load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def validate_file(yaml_path: Path, schema: dict) -> list[str]:
    """Validate a single YAML file. Returns list of error messages (empty if valid)."""
    errors = []

    try:
        with open(yaml_path) as f:
            entries = list(yaml.safe_load_all(f))
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]

    for i, entry in enumerate(entries):
        if entry is None:
            continue
        if not isinstance(entry, dict):
            errors.append(f"Entry {i}: expected dict, got {type(entry).__name__}")
            continue

        try:
            validate(instance=entry, schema=schema)
        except ValidationError as e:
            path = ".".join(str(p) for p in e.path) if e.path else "root"
            errors.append(f"Entry {i} ({entry.get('package', '?')}): {e.message} at path '{path}'")

    return errors


def validate_all() -> bool:
    """Validate all YAML files. Returns True if all valid."""
    schema = load_schema()
    all_valid = True
    total_files = 0
    total_errors = 0

    for data_dir in DATA_DIRS:
        if not data_dir.exists():
            continue

        for yaml_file in sorted(data_dir.glob("*.yaml")):
            total_files += 1
            errors = validate_file(yaml_file, schema)

            if errors:
                all_valid = False
                total_errors += len(errors)
                print(f"FAIL: {yaml_file.relative_to(ROOT)}")
                for err in errors:
                    print(f"  - {err}")
            else:
                print(f"PASS: {yaml_file.relative_to(ROOT)}")

    print(f"\n{total_files} files checked, {total_errors} errors found")
    return all_valid


if __name__ == "__main__":
    if validate_all():
        print("\nAll entries valid!")
        sys.exit(0)
    else:
        print("\nValidation failed!", file=sys.stderr)
        sys.exit(1)
