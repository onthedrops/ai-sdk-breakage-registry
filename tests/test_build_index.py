"""Tests for the index builder."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from build_index import build_index


class TestBuildIndex:
    def test_build_index_returns_dict(self):
        index = build_index()
        assert isinstance(index, dict)

    def test_index_has_version(self):
        index = build_index()
        assert "version" in index

    def test_index_has_entries(self):
        index = build_index()
        assert "entries" in index
        assert len(index["entries"]) >= 5, "Expected at least 5 entries"

    def test_index_has_generated_at(self):
        index = build_index()
        assert "generated_at" in index

    def test_index_total_matches_entries(self):
        index = build_index()
        assert index["total_entries"] == len(index["entries"])

    def test_each_entry_has_required_fields(self):
        index = build_index()
        required = ["package", "ecosystem", "from_version_range", "to_version_range"]
        for entry in index["entries"]:
            for field in required:
                assert field in entry, f"Entry missing {field}: {entry.get('package', '?')}"

    def test_entries_have_source_file(self):
        index = build_index()
        for entry in index["entries"]:
            assert "_source_file" in entry
