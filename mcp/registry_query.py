"""Query layer over the AI SDK breakage registry.

Pure data access with no MCP dependency so it can be tested standalone.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

REGISTRY_URL = (
    "https://raw.githubusercontent.com/onthedrops/ai-sdk-breakage-registry"
    "/main/generated/registry.json"
)

# The copy generated from the YAML sources in this repo.
LOCAL_REGISTRY = Path(__file__).resolve().parent.parent / "generated" / "registry.json"

CACHE_PATH = Path(
    os.environ.get("AI_SDK_BREAKAGE_CACHE_DIR", str(Path.home() / ".cache" / "ai-sdk-breakage"))
) / "registry.json"

CACHE_TTL_SECONDS = 7 * 24 * 60 * 60


def _cache_is_fresh(path: Path = CACHE_PATH) -> bool:
    try:
        return path.exists() and (time.time() - path.stat().st_mtime) < CACHE_TTL_SECONDS
    except OSError:
        return False


def _fetch_remote(timeout: int = 10) -> Optional[dict]:
    try:
        import urllib.request

        with urllib.request.urlopen(REGISTRY_URL, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        return None
    if not data["entries"]:
        return None
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, CACHE_PATH)
    except OSError:
        pass
    return data


def load_registry(refresh: bool = False) -> dict:
    """Load the registry document.

    Prefers the in-repo generated copy (always current when the server runs
    from a checkout), then a cached download, then a fresh download.
    """
    if not refresh and LOCAL_REGISTRY.exists():
        try:
            with open(LOCAL_REGISTRY) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    if refresh or not _cache_is_fresh():
        data = _fetch_remote()
        if data is not None:
            return data

    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    return {"entries": [], "total_changes": 0}


def _norm(s: str) -> str:
    """Normalize a symbol for comparison: lowercase, strip call parens/args."""
    s = s.strip().lower()
    s = re.sub(r"\(.*?\)", "", s)
    return s.strip(" .")


def list_packages(registry: dict) -> list[dict[str, Any]]:
    """One row per registry entry, without the change bodies."""
    out = []
    for e in registry.get("entries", []):
        out.append(
            {
                "package": e.get("package", ""),
                "ecosystem": e.get("ecosystem", ""),
                "from_version_range": e.get("from_version_range", ""),
                "to_version_range": e.get("to_version_range", ""),
                "severity": e.get("severity", ""),
                "change_count": len(e.get("changes", [])),
                "last_verified": e.get("last_verified", ""),
                "confidence": e.get("confidence", ""),
                "summary": e.get("summary", ""),
            }
        )
    return sorted(out, key=lambda r: (r["package"], r["ecosystem"]))


def _boundary_match(needle: str, term: str) -> bool:
    """True if `term` appears in `needle` as a whole dotted-path token.

    Prevents short symbols like "chat" from matching inside unrelated
    identifiers such as "openai.chatcompletion.create".
    """
    if not term:
        return False
    return re.search(r"(?<![\w.])" + re.escape(term) + r"(?![\w])", needle) is not None


def check_symbol(registry: dict, symbol: str, package: Optional[str] = None) -> list[dict[str, Any]]:
    """Find changes whose deprecated symbol or detection regex matches `symbol`.

    This is the pre-generation check: given code an agent is about to emit,
    report whether it targets an API that has already broken. Results are
    ranked most-specific first.
    """
    needle = _norm(symbol)
    if not needle:
        return []

    hits = []
    for e in registry.get("entries", []):
        if package and e.get("package", "").lower() != package.lower():
            continue
        for c in e.get("changes", []):
            before = _norm(c.get("symbol_before", ""))
            score = 0

            if before and before == needle:
                score = 3
            elif before and (_boundary_match(needle, before) or _boundary_match(before, needle)):
                score = 2

            if score == 0:
                for pattern in c.get("detection", {}).get("regex", []) or []:
                    try:
                        if re.search(pattern, symbol, re.IGNORECASE):
                            score = 2
                            break
                    except re.error:
                        continue

            if score:
                hits.append(
                    (
                        score,
                        {
                            "package": e.get("package", ""),
                            "ecosystem": e.get("ecosystem", ""),
                            "severity": e.get("severity", ""),
                            "broke_in": e.get("to_version_range", ""),
                            "symbol_before": c.get("symbol_before", ""),
                            "symbol_after": c.get("symbol_after", ""),
                            "change_type": c.get("change_type", ""),
                            "migration_note": c.get("migration_note", ""),
                            "before": c.get("before", ""),
                            "after": c.get("after", ""),
                            "last_verified": e.get("last_verified", ""),
                            "confidence": e.get("confidence", ""),
                        },
                    )
                )

    hits.sort(key=lambda h: -h[0])
    return [h[1] for h in hits]


def get_package(
    registry: dict,
    package: str,
    ecosystem: Optional[str] = None,
    include_examples: bool = False,
) -> list[dict[str, Any]]:
    """All registry entries for a package, optionally with code examples."""
    out = []
    for e in registry.get("entries", []):
        if e.get("package", "").lower() != package.lower():
            continue
        if ecosystem and e.get("ecosystem", "").lower() != ecosystem.lower():
            continue
        changes = []
        for c in e.get("changes", []):
            row = {
                "symbol_before": c.get("symbol_before", ""),
                "symbol_after": c.get("symbol_after", ""),
                "change_type": c.get("change_type", ""),
                "migration_note": c.get("migration_note", ""),
            }
            if include_examples:
                row["before"] = c.get("before", "")
                row["after"] = c.get("after", "")
            changes.append(row)
        out.append(
            {
                "package": e.get("package", ""),
                "ecosystem": e.get("ecosystem", ""),
                "from_version_range": e.get("from_version_range", ""),
                "to_version_range": e.get("to_version_range", ""),
                "severity": e.get("severity", ""),
                "category": e.get("category", ""),
                "summary": e.get("summary", ""),
                "last_verified": e.get("last_verified", ""),
                "confidence": e.get("confidence", ""),
                "sources": e.get("sources", []),
                "changes": changes,
            }
        )
    return out


def search(registry: dict, query: str, limit: int = 20) -> list[dict[str, Any]]:
    """Free-text search across summaries, symbols, and migration notes."""
    q = query.strip().lower()
    if not q:
        return []
    hits = []
    for e in registry.get("entries", []):
        haystack_entry = " ".join(
            [e.get("package", ""), e.get("summary", ""), e.get("category", "")]
        ).lower()
        for c in e.get("changes", []):
            haystack = " ".join(
                [
                    haystack_entry,
                    c.get("symbol_before", ""),
                    c.get("symbol_after", ""),
                    c.get("migration_note", ""),
                    c.get("change_type", ""),
                ]
            ).lower()
            if q in haystack:
                hits.append(
                    {
                        "package": e.get("package", ""),
                        "ecosystem": e.get("ecosystem", ""),
                        "symbol_before": c.get("symbol_before", ""),
                        "symbol_after": c.get("symbol_after", ""),
                        "migration_note": c.get("migration_note", ""),
                        "severity": e.get("severity", ""),
                    }
                )
                if len(hits) >= limit:
                    return hits
    return hits
