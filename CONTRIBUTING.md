# Contributing to the AI SDK Breaking Changes Registry

Thank you for your interest in contributing. This registry is community-maintained — every contribution helps developers catch breaking changes before they hit production.

## Ways to Contribute

### 1. Add a new SDK or version migration

Each SDK has a YAML file in `data/pypi/` or `data/npm/`. To add coverage for a new package or version transition:

1. **Research the breaking changes** — read the official migration guide, changelog, or release notes. We only accept changes documented in official sources.
2. **Create a YAML file** — see `data/pypi/openai.yaml` for the canonical format example.
3. **Run verification** — `python scripts/verify_registry.py` checks that all regexes compile, match their `before` blocks, and that change types are valid.
4. **Submit a PR** with a clear title like `Add <package> <from_version> → <to_version>`.

### 2. Improve an existing entry

Found a missing change, an incorrect regex, or a better migration note? Edit the YAML file directly and submit a PR. Run `python scripts/verify_registry.py` before submitting.

### 3. Report a missing breaking change

Open an issue with:
- Package name and version transition
- The deprecated code pattern
- The new code pattern
- Link to official documentation

### 4. Improve auto-fix rules

Auto-fix rules live in the [devcheck-ai](https://github.com/onthedrops/devcheck-ai) companion tool. If a registry entry has a safe one-line transformation that can be auto-fixed, propose a rule there.

## YAML Entry Format

```yaml
package: example-package
ecosystem: pypi
from_version_range: "<2.0.0"
to_version_range: ">=2.0.0"
severity: high
category: api_break
summary: "Brief description of the migration"

changes:
  - symbol_before: "old_function()"
    symbol_after: "new_function()"
    change_type: renamed_function
    before: |
      from example import old_function
      result = old_function()
    after: |
      from example import new_function
      result = new_function()
    detection:
      regex:
        - "old_function\("
    migration_note: "old_function was renamed to new_function in v2.0"

sources:
  - title: "Migration Guide"
    url: "https://example.com/docs/migration"

last_verified: "2026-08-28"
confidence: high
```

### Valid change_type values

`import_path_changed`, `renamed_function`, `renamed_method`, `renamed_class`, `method_renamed`, `removed_method`, `removed_class`, `parameter_required`, `parameter_removed`, `parameter_renamed`, `api_removed`, `behavior_changed`, `default_behavior_changed`, `return_type_changed`, `platform_requirement_added`

### Rules for detection regexes

- Use **single backslashes** in single-quoted YAML strings (e.g. `'\.foo\('` not `'\\.foo\\('`)
- Every regex **must match** something in its `before` code block — the verification script checks this
- Prefer patterns that match real deprecated code, not comments or string literals

## Verification

Before submitting a PR, run:

```bash
python scripts/verify_registry.py
```

This checks:
- YAML structure and required fields
- All change_type values are valid
- All detection regexes compile
- Each regex matches its corresponding `before` block (self-consistency)
- No duplicate symbols across packages
- All source URLs have valid syntax

## Code of Conduct

Be respectful. Be constructive. Cite sources. Don't add entries from AI-generated descriptions — only from official documentation.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
