"""Tests for the registry query layer (no MCP dependency required)."""

import json
import time

import pytest

import registry_query as rq


@pytest.fixture(scope="module")
def registry():
    return rq.load_registry()


class TestLoad:
    def test_loads_entries(self, registry):
        assert len(registry["entries"]) > 0

    def test_local_copy_is_used(self):
        assert rq.LOCAL_REGISTRY.exists()

    def test_rejects_payload_without_entries(self, monkeypatch, tmp_path):
        monkeypatch.setattr(rq, "CACHE_PATH", tmp_path / "r.json")
        monkeypatch.setattr(rq, "LOCAL_REGISTRY", tmp_path / "absent.json")

        class FakeResp:
            def read(self):
                return json.dumps({"version": "1"}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResp())
        assert rq._fetch_remote() is None

    def test_cache_freshness(self, tmp_path):
        p = tmp_path / "r.json"
        p.write_text("{}")
        assert rq._cache_is_fresh(p) is True
        assert rq._cache_is_fresh(tmp_path / "missing.json") is False


class TestCheckSymbol:
    def test_finds_openai_chatcompletion(self, registry):
        hits = rq.check_symbol(registry, "openai.ChatCompletion.create")
        assert hits
        assert hits[0]["package"] == "openai"
        assert "chat.completions.create" in hits[0]["symbol_after"]

    def test_finds_anthropic_completions(self, registry):
        hits = rq.check_symbol(registry, "client.completions.create")
        assert hits[0]["package"] == "anthropic"

    def test_no_false_positive_on_clean_code(self, registry):
        assert rq.check_symbol(registry, "json.dumps(payload)") == []

    def test_short_symbol_does_not_match_inside_identifier(self, registry):
        """'chat' must not match inside 'openai.chatcompletion.create'."""
        hits = rq.check_symbol(registry, "openai.ChatCompletion.create")
        assert all(h["package"] != "cohere" for h in hits)

    def test_exact_match_ranks_first(self, registry):
        hits = rq.check_symbol(registry, "openai.ChatCompletion.create")
        assert hits[0]["symbol_before"] == "openai.ChatCompletion.create"

    def test_package_filter(self, registry):
        hits = rq.check_symbol(registry, "client.completions.create", package="anthropic")
        assert all(h["package"] == "anthropic" for h in hits)

    def test_empty_symbol_returns_empty(self, registry):
        assert rq.check_symbol(registry, "   ") == []

    def test_matches_full_line_of_code(self, registry):
        hits = rq.check_symbol(registry, "openai.api_key = os.environ['KEY']")
        assert any(h["package"] == "openai" for h in hits)


class TestGetPackage:
    def test_returns_entry(self, registry):
        entries = rq.get_package(registry, "langchain")
        assert entries and entries[0]["package"] == "langchain"

    def test_examples_excluded_by_default(self, registry):
        entries = rq.get_package(registry, "openai")
        assert "before" not in entries[0]["changes"][0]

    def test_examples_included_on_request(self, registry):
        entries = rq.get_package(registry, "openai", include_examples=True)
        assert "before" in entries[0]["changes"][0]

    def test_unknown_package_returns_empty(self, registry):
        assert rq.get_package(registry, "definitely-not-real") == []

    def test_ecosystem_filter(self, registry):
        entries = rq.get_package(registry, "openai", ecosystem="pypi")
        assert all(e["ecosystem"] == "pypi" for e in entries)


class TestSearchAndList:
    def test_search_finds_results(self, registry):
        assert rq.search(registry, "streaming")

    def test_search_respects_limit(self, registry):
        assert len(rq.search(registry, "a", limit=3)) <= 3

    def test_search_empty_query(self, registry):
        assert rq.search(registry, "") == []

    def test_list_packages_sorted_and_complete(self, registry):
        rows = rq.list_packages(registry)
        assert len(rows) == len(registry["entries"])
        assert rows == sorted(rows, key=lambda r: (r["package"], r["ecosystem"]))

    def test_list_packages_has_freshness(self, registry):
        assert all(r["last_verified"] for r in rq.list_packages(registry))
