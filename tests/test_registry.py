"""Tests for the AI SDK Breakage Registry."""

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
SCHEMA_PATH = ROOT / "schema" / "breaking-change.schema.json"
DATA_DIRS = [ROOT / "data" / "pypi", ROOT / "data" / "npm"]


def load_schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def load_all_entries():
    """Load all YAML entries from data directories."""
    entries = []
    for data_dir in DATA_DIRS:
        if not data_dir.exists():
            continue
        for yaml_file in sorted(data_dir.glob("*.yaml")):
            with open(yaml_file) as f:
                file_entries = list(yaml.safe_load_all(f))
                for entry in file_entries:
                    if entry is not None:
                        entries.append((yaml_file, entry))
    return entries


class TestSchema:
    def test_schema_exists(self):
        assert SCHEMA_PATH.exists()

    def test_schema_is_valid_json(self):
        schema = load_schema()
        assert isinstance(schema, dict)
        assert schema["type"] == "object"
        assert "required" in schema


class TestEntries:
    def test_all_entries_have_required_fields(self):
        schema = load_schema()
        required_fields = schema["required"]
        entries = load_all_entries()

        assert len(entries) > 0, "No entries found"

        for yaml_path, entry in entries:
            for field in required_fields:
                assert field in entry, (
                    f"{yaml_path.name}: missing required field '{field}'"
                )

    def test_all_entries_have_valid_ecosystem(self):
        entries = load_all_entries()
        valid = {"pypi", "npm"}

        for yaml_path, entry in entries:
            assert entry["ecosystem"] in valid, (
                f"{yaml_path.name}: invalid ecosystem '{entry['ecosystem']}'"
            )

    def test_all_entries_have_valid_severity(self):
        entries = load_all_entries()
        valid = {"low", "medium", "high", "critical"}

        for yaml_path, entry in entries:
            assert entry["severity"] in valid, (
                f"{yaml_path.name}: invalid severity '{entry['severity']}'"
            )

    def test_all_entries_have_at_least_one_change(self):
        entries = load_all_entries()

        for yaml_path, entry in entries:
            changes = entry.get("changes", [])
            assert len(changes) > 0, (
                f"{yaml_path.name}: no changes defined"
            )

    def test_all_entries_have_sources_with_urls(self):
        entries = load_all_entries()

        for yaml_path, entry in entries:
            sources = entry.get("sources", [])
            assert len(sources) > 0, f"{yaml_path.name}: no sources"
            for source in sources:
                assert "title" in source, f"{yaml_path.name}: source missing title"
                assert "url" in source, f"{yaml_path.name}: source missing url"
                assert source["url"].startswith("http"), (
                    f"{yaml_path.name}: source URL doesn't start with http"
                )

    def test_all_changes_have_before_and_after(self):
        entries = load_all_entries()

        for yaml_path, entry in entries:
            for i, change in enumerate(entry.get("changes", [])):
                assert "before" in change, (
                    f"{yaml_path.name}: change {i} missing 'before'"
                )
                assert "after" in change, (
                    f"{yaml_path.name}: change {i} missing 'after'"
                )
                assert "change_type" in change, (
                    f"{yaml_path.name}: change {i} missing 'change_type'"
                )

    def test_all_entries_have_detection_patterns(self):
        entries = load_all_entries()

        for yaml_path, entry in entries:
            for i, change in enumerate(entry.get("changes", [])):
                detection = change.get("detection", {})
                if detection:
                    assert "regex" in detection or "import_patterns" in detection, (
                        f"{yaml_path.name}: change {i} has detection but no regex or import_patterns"
                    )

    def test_openai_pypi_entry_exists(self):
        entries = load_all_entries()
        openai_entries = [
            (p, e) for p, e in entries
            if e["package"] == "openai" and e["ecosystem"] == "pypi"
        ]
        assert len(openai_entries) > 0, "No openai pypi entry found"

    def test_openai_npm_entry_exists(self):
        entries = load_all_entries()
        openai_entries = [
            (p, e) for p, e in entries
            if e["package"] == "openai" and e["ecosystem"] == "npm"
        ]
        assert len(openai_entries) > 0, "No openai npm entry found"

    def test_langchain_entry_exists(self):
        entries = load_all_entries()
        lc_entries = [e for _, e in entries if e["package"] == "langchain"]
        assert len(lc_entries) > 0, "No langchain entry found"

    def test_anthropic_entry_exists(self):
        entries = load_all_entries()
        ant_entries = [e for _, e in entries if e["package"] == "anthropic"]
        assert len(ant_entries) > 0, "No anthropic entry found"

    def test_vercel_ai_sdk_entries_exist(self):
        entries = load_all_entries()
        ai_entries = [e for _, e in entries if e["package"] == "ai"]
        assert len(ai_entries) >= 2, f"Expected 2+ vercel ai entries, got {len(ai_entries)}"

    def test_google_pypi_entry_exists(self):
        entries = load_all_entries()
        google_entries = [
            (p, e) for p, e in entries
            if e["package"] == "google-generativeai" and e["ecosystem"] == "pypi"
        ]
        assert len(google_entries) > 0, "No google-generativeai pypi entry found"

    def test_google_vertex_entry_exists(self):
        entries = load_all_entries()
        vertex_entries = [
            (p, e) for p, e in entries
            if e["package"] == "google-cloud-aiplatform"
        ]
        assert len(vertex_entries) > 0, "No google-cloud-aiplatform entry found"

    def test_google_npm_entry_exists(self):
        entries = load_all_entries()
        google_npm = [
            (p, e) for p, e in entries
            if e["package"] == "@google/generative-ai" and e["ecosystem"] == "npm"
        ]
        assert len(google_npm) > 0, "No @google/generative-ai npm entry found"

    def test_transformers_entry_exists(self):
        entries = load_all_entries()
        tf_entries = [e for _, e in entries if e["package"] == "transformers"]
        assert len(tf_entries) > 0, "No transformers entry found"
