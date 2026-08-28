#!/usr/bin/env python3
"""Verify registry entries for structural integrity and self-consistency.

Deterministic checks (always run):
  - YAML parses without errors
  - Required top-level fields exist on every package entry
  - Every change has: symbol_before, change_type, before, after, migration_note
  - symbol_after required unless change_type is api_removed (empty replacement)
  - Every detection regex compiles as valid Python regex
  - At least one detection regex matches the entry's own `before` code block
  - source URLs are syntactically valid HTTP(S)
  - No duplicate (symbol_before + change_type + regex) within the same package
  - generated/registry.json matches YAML sources (calls build_registry.py --check)

Optional checks (behind --check-urls):
  - Every source URL returns HTTP 200 (with HEAD -> GET fallback)
  - Reports dead links as warnings (non-blocking on first run)

Optional checks (behind --check-content):
  - Fetches all source URLs for each package, extracts text, builds a corpus
  - Verifies that key API terms from each change appear in the source corpus
  - Detects content drift: documentation pages that no longer mention the API
  - JS-rendered pages with minimal text are marked unverifiable (warning, not error)
  - GitHub blob URLs are auto-converted to raw.githubusercontent.com for reliable text fetch

Usage:
    python scripts/verify_registry.py                  # deterministic checks
    python scripts/verify_registry.py --check-urls     # also verify URL liveness
    python scripts/verify_registry.py --check-content  # also verify content at source URLs
    python scripts/verify_registry.py --strict         # warnings become errors
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_PYPI = ROOT / "data" / "pypi"
DATA_NPM = ROOT / "data" / "npm"

REQUIRED_PKG_FIELDS = {"package", "ecosystem", "from_version_range", "to_version_range", "changes", "sources"}
REQUIRED_CHANGE_FIELDS = {"symbol_before", "change_type", "before", "after", "migration_note"}

VALID_CHANGE_TYPES = {
    "import_path_changed",
    "renamed_function",
    "renamed_method",
    "renamed_class",
    "method_renamed",
    "removed_method",
    "removed_class",
    "parameter_required",
    "parameter_removed",
    "parameter_renamed",
    "api_removed",
    "behavior_changed",
    "default_behavior_changed",
    "return_type_changed",
    "platform_requirement_added",
}

VALID_ECOSYSTEMS = {"pypi", "npm"}


class CheckResult:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.passed: int = 0

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    def ok(self):
        self.passed += 1

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def report(self, strict: bool = False) -> int:
        fail = self.errors if not strict else self.errors + self.warnings
        for msg in self.warnings:
            print(f"  WARNING: {msg}")
        for msg in self.errors:
            print(f"  ERROR: {msg}")
        print(f"\n  {self.passed} checks passed, {len(self.warnings)} warnings, {len(self.errors)} errors")
        if fail:
            return 1
        return 0


def load_all_yaml() -> list[tuple[pathlib.Path, dict]]:
    """Load all YAML source files from data/pypi/ and data/npm/."""
    entries = []
    for eco_dir in [DATA_PYPI, DATA_NPM]:
        if not eco_dir.exists():
            continue
        for yaml_file in sorted(eco_dir.glob("*.yaml")):
            with open(yaml_file) as f:
                try:
                    data = yaml.safe_load(f)
                    if data is not None:
                        entries.append((yaml_file, data))
                except yaml.YAMLError as e:
                    print(f"  ERROR: {yaml_file.name}: YAML parse error: {e}")
                    sys.exit(1)
    return entries


def check_structure(result: CheckResult, yaml_path: pathlib.Path, entry: dict):
    """Check that required top-level fields exist."""
    for field in REQUIRED_PKG_FIELDS:
        if field not in entry:
            result.error(f"{yaml_path.name}: missing required field '{field}'")

    if entry.get("ecosystem") and entry["ecosystem"] not in VALID_ECOSYSTEMS:
        result.error(f"{yaml_path.name}: invalid ecosystem '{entry['ecosystem']}'")

    changes = entry.get("changes", [])
    if not changes:
        result.error(f"{yaml_path.name}: no changes defined")
        return

    for i, change in enumerate(changes):
        prefix = f"{yaml_path.name}: change {i} ({change.get('symbol_before', '?')})"

        for field in REQUIRED_CHANGE_FIELDS:
            if field not in change:
                result.error(f"{prefix}: missing required field '{field}'")

        ct = change.get("change_type", "")
        if ct and ct not in VALID_CHANGE_TYPES:
            result.error(f"{prefix}: invalid change_type '{ct}'")

        # symbol_after can be empty only for api_removed
        if not change.get("symbol_after") and ct != "api_removed":
            result.error(f"{prefix}: symbol_after is empty but change_type is '{ct}' (only api_removed allows empty)")

        # migration_note should be non-empty
        if not change.get("migration_note", "").strip():
            result.error(f"{prefix}: migration_note is empty")

        result.ok()


def check_regex_compiles(result: CheckResult, yaml_path: pathlib.Path, entry: dict):
    """Check that all detection regex patterns compile."""
    for i, change in enumerate(entry.get("changes", [])):
        detection = change.get("detection", {})
        if not detection:
            continue

        regexes = detection.get("regex", [])
        if not regexes:
            regexes = detection.get("import_patterns", [])

        for j, pattern in enumerate(regexes):
            prefix = f"{yaml_path.name}: change {i} regex {j}"
            try:
                re.compile(pattern)
                result.ok()
            except re.error as e:
                result.error(f"{prefix}: invalid regex: {e}")


def check_self_consistency(result: CheckResult, yaml_path: pathlib.Path, entry: dict):
    """Check that detection regexes actually match the entry's own 'before' code."""
    for i, change in enumerate(entry.get("changes", [])):
        detection = change.get("detection", {})
        before_code = change.get("before", "")
        symbol = change.get("symbol_before", "?")

        if not detection or not before_code:
            continue

        regexes = detection.get("regex", [])
        if not regexes:
            regexes = detection.get("import_patterns", [])

        if not regexes:
            continue

        # At least one regex should match the before block
        matched = False
        for pattern in regexes:
            try:
                if re.search(pattern, before_code):
                    matched = True
                    break
            except re.error:
                pass  # Already caught in check_regex_compiles

        if not matched:
            result.error(
                f"{yaml_path.name}: change {i} ({symbol}): "
                f"no detection regex matches the 'before' code block"
            )
        else:
            result.ok()


def check_symbol_containment(result: CheckResult, yaml_path: pathlib.Path, entry: dict):
    """Soft check: symbol_before should appear in the before code block."""
    for i, change in enumerate(entry.get("changes", [])):
        symbol_before = change.get("symbol_before", "")
        before_code = change.get("before", "")
        symbol_after = change.get("symbol_after", "")
        after_code = change.get("after", "")

        if symbol_before and before_code:
            # Extract the core identifier from symbol_before (first token before any space or paren)
            core = re.split(r"[\s(]", symbol_before.strip())[0]
            # For dotted symbols like "chain.run(query)", check the last component
            parts = core.split(".")
            check_token = parts[-1] if len(parts) > 1 else core

            if check_token and len(check_token) > 2:
                if check_token not in before_code:
                    result.warn(
                        f"{yaml_path.name}: change {i}: "
                        f"'{check_token}' from symbol_before not found in 'before' code"
                    )

        # For symbol_after, only check if after is non-empty and symbol_after is non-empty
        if symbol_after and after_code:
            core = re.split(r"[\s(]", symbol_after.strip())[0]
            parts = core.split(".")
            check_token = parts[-1] if len(parts) > 1 else core

            if check_token and len(check_token) > 2:
                if check_token not in after_code:
                    result.warn(
                        f"{yaml_path.name}: change {i}: "
                        f"'{check_token}' from symbol_after not found in 'after' code"
                    )

        result.ok()


def check_url_syntax(result: CheckResult, yaml_path: pathlib.Path, entry: dict):
    """Check that source URLs are syntactically valid HTTP(S)."""
    sources = entry.get("sources", [])
    for j, source in enumerate(sources):
        url = source.get("url", "")
        title = source.get("title", "")

        if not title:
            result.error(f"{yaml_path.name}: source {j}: missing title")

        if not url:
            result.error(f"{yaml_path.name}: source {j}: missing URL")
            continue

        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            result.error(f"{yaml_path.name}: source {j}: URL must be HTTP(S), got '{parsed.scheme}'")
        elif not parsed.netloc:
            result.error(f"{yaml_path.name}: source {j}: URL has no domain")
        else:
            result.ok()


def check_url_liveness(result: CheckResult, yaml_path: pathlib.Path, entry: dict):
    """Check that source URLs return HTTP 200 (optional, network-dependent)."""
    sources = entry.get("sources", [])
    for j, source in enumerate(sources):
        url = source.get("url", "")
        if not url:
            continue

        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue  # Already caught in syntax check

        try:
            # Try HEAD first, fallback to GET
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "ai-sdk-breakage-registry-verify/1.0"})
            try:
                resp = urllib.request.urlopen(req, timeout=15)
                status = resp.status
                resp.close()
            except urllib.error.HTTPError as e:
                if e.code == 405:  # HEAD not allowed, try GET
                    req = urllib.request.Request(url, headers={"User-Agent": "ai-sdk-breakage-registry-verify/1.0"})
                    resp = urllib.request.urlopen(req, timeout=15)
                    status = resp.status
                    resp.close()
                else:
                    raise

            if 200 <= status < 400:
                result.ok()
            else:
                result.warn(f"{yaml_path.name}: source {j} ({url}): HTTP {status}")
        except Exception as e:
            result.warn(f"{yaml_path.name}: source {j} ({url}): {e}")


def check_duplicates(result: CheckResult, yaml_path: pathlib.Path, entry: dict):
    """Check for duplicate entries within the same package."""
    seen: dict[str, str] = {}
    package = entry.get("package", "?")

    for i, change in enumerate(entry.get("changes", [])):
        symbol_before = change.get("symbol_before", "")
        change_type = change.get("change_type", "")

        detection = change.get("detection", {})
        regexes = tuple(detection.get("regex", detection.get("import_patterns", [])))

        key = f"{symbol_before}|{change_type}|{regexes}"

        if key in seen:
            result.error(
                f"{yaml_path.name}: duplicate entry detected — "
                f"change {seen[key]} and change {i} have identical "
                f"symbol_before='{symbol_before}', change_type='{change_type}', regexes={regexes}"
            )
        else:
            seen[key] = str(i)

    result.ok()


# ── Content verification helpers ──

# Tokens that are too generic to be useful for content matching
_GENERIC_TOKENS = {
    "client", "model", "result", "input", "use", "string", "run", "agent",
    "chain", "tool", "config", "create", "import", "from", "call", "text",
    "response", "query", "data", "file", "name", "type", "value", "class",
    "function", "method", "param", "parameter", "args", "kwargs", "self",
    "return", "true", "false", "none", "null", "async", "await", "new",
    "const", "let", "var", "def", "init", "main",
}


def extract_verification_terms(change: dict) -> list[str]:
    """Extract strong API-specific terms from a change entry for content matching.

    Returns a list of terms that should appear in the official source documentation.
    These are concrete API names, class names, method names, import paths —
    not generic programming keywords.
    """
    terms: set[str] = set()

    # Pull from symbol_before and symbol_after
    for field in ("symbol_before", "symbol_after"):
        val = change.get(field, "")
        if not val:
            continue
        # Extract dotted paths, function names, class names
        # Match identifiers, dotted paths, and decorators
        for token in re.findall(r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*', val):
            parts = token.split(".")
            # Add the full dotted path if it has 2+ parts
            if len(parts) >= 2:
                terms.add(token)
            # Add each non-generic component
            for part in parts:
                if len(part) > 3 and part.lower() not in _GENERIC_TOKENS:
                    terms.add(part)
            # For import paths, add the module part
            if len(parts) >= 3:
                terms.add(parts[0] + "." + parts[1])

    # Pull from before/after code blocks
    for field in ("before", "after"):
        code = change.get(field, "")
        if not code:
            continue
        # Extract import statements
        for m in re.finditer(r'(?:from|import)\s+([A-Za-z_][A-Za-z0-9_.]*)', code):
            terms.add(m.group(1))
            parts = m.group(1).split(".")
            if len(parts) >= 2:
                terms.add(parts[-1])
        # Extract class/function names from definitions and calls
        for m in re.finditer(r'(?:class|def|@)\s*([A-Za-z_][A-Za-z0-9_]*)', code):
            name = m.group(1)
            if len(name) > 3 and name.lower() not in _GENERIC_TOKENS:
                terms.add(name)
        # Extract method calls like obj.method_name(
        for m in re.finditer(r'\.([a-z_][A-Za-z0-9_]*)\s*\(', code):
            name = m.group(1)
            if len(name) > 3 and name.lower() not in _GENERIC_TOKENS:
                terms.add(name)

    # Pull from detection regexes — extract literal strings
    detection = change.get("detection", {})
    regexes = detection.get("regex", detection.get("import_patterns", []))
    for pattern in regexes:
        # Extract literal strings from regex (text between quotes)
        for m in re.finditer(r'"([A-Za-z_][A-Za-z0-9_.]+)"', pattern):
            terms.add(m.group(1))
        # Extract unescaped identifiers
        for m in re.finditer(r'([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)', pattern):
            terms.add(m.group(1))

    # Filter out generic tokens and very short tokens
    filtered = {t for t in terms if len(t) > 3 and t.lower() not in _GENERIC_TOKENS}

    return sorted(filtered)


def github_blob_to_raw(url: str) -> str:
    """Convert github.com blob URLs to raw.githubusercontent.com for reliable text fetch."""
    # https://github.com/org/repo/blob/branch/path -> https://raw.githubusercontent.com/org/repo/branch/path
    m = re.match(r'https://github\.com/([^/]+)/([^/]+)/blob/(.+)', url)
    if m:
        return f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return url


def strip_html(raw_html: str) -> str:
    """Extract readable text from HTML, stripping tags and scripts."""
    # Remove script and style blocks entirely
    text = re.sub(r'<script[^>]*>.*?</script>', '', raw_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Decode HTML entities
    text = html.unescape(text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower()


def fetch_url_content(url: str, timeout: int = 15, max_bytes: int = 2_000_000) -> str | None:
    """Fetch URL content and return extracted text, or None on failure."""
    # Convert GitHub blob URLs to raw for reliable text access
    url = github_blob_to_raw(url)

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ai-sdk-breakage-registry-verify/1.0", "Accept": "text/html,text/plain,*/*"},
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        content_type = resp.headers.get("Content-Type", "")
        # Read up to max_bytes
        raw = resp.read(max_bytes + 1).decode("utf-8", errors="replace")
        resp.close()

        if len(raw) > max_bytes:
            raw = raw[:max_bytes]

        # If it's HTML, strip tags; otherwise return as-is
        if "html" in content_type.lower() or raw.strip().startswith("<"):
            return strip_html(raw)
        return raw.lower()
    except Exception:
        return None


def is_js_rendered(text: str) -> bool:
    """Heuristic: detect pages that require JavaScript to render content."""
    if not text:
        return True
    # Very short text likely means JS-rendered
    if len(text.strip()) < 200:
        return True
    # Common JS-required indicators
    indicators = [
        "enable javascript",
        "please enable js",
        "requires javascript",
        "you need javascript",
        "javascript is required",
        "loading...",
        "<noscript>",
    ]
    text_lower = text.lower()
    for indicator in indicators:
        if indicator in text_lower:
            return True
    return False


def check_content_verification(
    result: CheckResult,
    entries: list[tuple[pathlib.Path, dict]],
):
    """Fetch source URLs for each package, build a corpus, and verify terms."""
    # Collect all unique URLs across all entries
    all_urls: set[str] = set()
    for yaml_path, entry in entries:
        for source in entry.get("sources", []):
            url = source.get("url", "")
            if url and url.startswith("http"):
                all_urls.add(url)

    print(f"  Fetching {len(all_urls)} unique source URLs...")

    # Fetch and cache content for each URL
    url_cache: dict[str, str | None] = {}
    js_rendered_count = 0
    failed_count = 0

    for i, url in enumerate(sorted(all_urls)):
        raw_url = github_blob_to_raw(url)
        text = fetch_url_content(url)
        url_cache[url] = text

        if text is None:
            failed_count += 1
            result.warn(f"Content fetch failed: {url}")
        elif is_js_rendered(text):
            js_rendered_count += 1
            result.warn(f"Content unverifiable (JS-rendered): {url}")

        # Rate limit between requests
        if i < len(all_urls) - 1:
            time.sleep(0.3)

    print(f"  Fetched: {len(url_cache)} URLs, {js_rendered_count} JS-rendered, {failed_count} failed")

    # For each package entry, build a corpus from its source URLs and verify terms
    total_checked = 0
    total_verified = 0
    total_unverified = 0

    for yaml_path, entry in entries:
        package = entry.get("package", "?")
        sources = entry.get("sources", [])

        # Build combined corpus from all source URLs for this package
        corpus_parts: list[str] = []
        for source in sources:
            url = source.get("url", "")
            if url in url_cache and url_cache[url]:
                corpus_parts.append(url_cache[url])

        if not corpus_parts:
            # All URLs failed for this package — already warned above
            continue

        corpus = " \n".join(corpus_parts)

        # Check each change's terms against the corpus
        for i, change in enumerate(entry.get("changes", [])):
            symbol = change.get("symbol_before", "?")
            terms = extract_verification_terms(change)

            if not terms:
                # No extractable terms (e.g., platform requirement)
                continue

            total_checked += 1

            # At least one strong term should appear in the corpus
            matched_terms = [t for t in terms if t.lower() in corpus]

            if matched_terms:
                total_verified += 1
                result.ok()
            else:
                total_unverified += 1
                result.warn(
                    f"{yaml_path.name}: change {i} ({symbol}): "
                    f"no API terms found in source documentation. "
                    f"Checked for: {', '.join(terms[:5])}"
                )

    print(f"  Content verification: {total_verified}/{total_checked} changes verified, "
          f"{total_unverified} unverifiable")


def main():
    args = sys.argv[1:]
    check_urls = "--check-urls" in args
    check_content = "--check-content" in args
    strict = "--strict" in args

    result = CheckResult()

    print("=" * 60)
    print("Registry Verification")
    print(f"  URL liveness check: {'ON' if check_urls else 'OFF'}")
    print(f"  Content verification: {'ON' if check_content else 'OFF'}")
    print(f"  Strict mode: {'ON' if strict else 'OFF'}")
    print("=" * 60)

    entries = load_all_yaml()
    if not entries:
        result.error("No YAML files found")
        print(result.report(strict))
        sys.exit(1)

    print(f"\nLoaded {len(entries)} YAML source files\n")

    # ── Deterministic checks ──
    print("── Structural Validation ──")
    for yaml_path, entry in entries:
        check_structure(result, yaml_path, entry)
    print(f"  {result.passed} structural checks passed\n")

    print("── Regex Compilation ──")
    for yaml_path, entry in entries:
        check_regex_compiles(result, yaml_path, entry)
    print(f"  {result.passed} regex compilation checks passed\n")

    print("── Self-Consistency (regex matches 'before' code) ──")
    for yaml_path, entry in entries:
        check_self_consistency(result, yaml_path, entry)
    print(f"  {result.passed} self-consistency checks passed\n")

    print("── Symbol Containment (soft check) ──")
    for yaml_path, entry in entries:
        check_symbol_containment(result, yaml_path, entry)
    print(f"  {result.passed} symbol containment checks passed\n")

    print("── URL Syntax Validation ──")
    for yaml_path, entry in entries:
        check_url_syntax(result, yaml_path, entry)
    print(f"  {result.passed} URL syntax checks passed\n")

    print("── Duplicate Detection ──")
    for yaml_path, entry in entries:
        check_duplicates(result, yaml_path, entry)
    print(f"  {result.passed} duplicate checks passed\n")

    print("── Registry JSON Sync ──")
    import subprocess
    sync_result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_registry.py"), "--check"],
        capture_output=True,
        text=True,
    )
    if sync_result.returncode == 0:
        result.ok()
        print(f"  {sync_result.stdout.strip()}\n")
    else:
        result.error(f"registry.json is out of sync with YAML sources")
        print(f"  {sync_result.stderr.strip()}\n")

    # ── Optional checks ──
    if check_urls:
        print("── URL Liveness Check (network) ──")
        for yaml_path, entry in entries:
            check_url_liveness(result, yaml_path, entry)
        print(f"  {result.passed} URL liveness checks passed\n")

    if check_content:
        print("── Content Verification (network) ──")
        check_content_verification(result, entries)
        print(f"  {result.passed} content checks passed\n")

    # ── Summary ──
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    exit_code = result.report(strict)

    if exit_code == 0:
        print("\nAll checks passed.")
    else:
        print(f"\n{len(result.errors)} error(s) found.")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
