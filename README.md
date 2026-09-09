# ai-sdk-breakage-registry

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Verify Registry](https://github.com/onthedrops/ai-sdk-breakage-registry/actions/workflows/verify-registry.yml/badge.svg)](https://github.com/onthedrops/ai-sdk-breakage-registry/actions/workflows/verify-registry.yml)
[![Tests](https://img.shields.io/badge/tests-53%20passing-brightgreen)](https://github.com/onthedrops/ai-sdk-breakage-registry)
[![Coverage](https://img.shields.io/badge/SDKs-20%20packages%20%7C%20244%20changes-blue)](https://github.com/onthedrops/ai-sdk-breakage-registry)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](CONTRIBUTING.md)

**A community-maintained, machine-readable registry of breaking changes in AI SDKs.**

When AI assistants write code, they may use SDK versions from their training data that have since shipped breaking changes. This registry maps specific version transitions to concrete code changes: renamed methods, removed parameters, changed return types, and new platform requirements — so tools like [devcheck-ai](https://github.com/onthedrops/devcheck-ai) can tell you **exactly what broke** when a version drifts, not just that it drifted.

## The Problem

```
AI assistant writes:  openai.ChatCompletion.create(model="gpt-4", ...)
You pip install:      openai 3.1.0 (the current version)
Result:               AttributeError: module 'openai' has no attribute 'ChatCompletion'
```

The AI used a 2-year-old API. The error message doesn't tell you what to do. This registry does.

## What's In the Registry

Each entry maps a version transition to specific breaking changes:

```yaml
package: openai
from_version_range: "<1.0.0"
to_version_range: ">=1.0.0"
changes:
  - symbol_before: "openai.ChatCompletion.create"
    symbol_after: "client.chat.completions.create"
    before: |
      import openai
      response = openai.ChatCompletion.create(...)
    after: |
      from openai import OpenAI
      client = OpenAI()
      response = client.chat.completions.create(...)
    detection:
      regex:
        - "openai\\.ChatCompletion\\.create"
```

Each change includes:
- **Before/after code examples** showing the exact migration
- **Detection patterns** (regex) that tools can use to scan codebases
- **Migration notes** explaining what to do
- **Official source URLs** for verification

## Covered SDKs

| Package | Ecosystem | Transition | Changes |
|---------|-----------|-----------|--------|
| `openai` | pypi | 0.x → 1.x | 7 |
| `openai` | npm | 3.x → 4.x | 5 |
| `anthropic` | pypi | <0.20 → >=0.20 | 3 |
| `@anthropic-ai/sdk` | npm | <0.34 → >=0.34 | 6 |
| `langchain` | pypi | 0.1.x → 0.2.x | 51 |
| `langchain` | pypi | 0.2.x → 1.x | 16 |
| `llamaindex` | pypi | <0.10 → >=0.10 | 17 |
| `pinecone` | pypi | <3.0 → >=3.0 | 10 |
| `weaviate-client` | pypi | <4.0 → >=4.0 | 13 |
| `chromadb` | pypi | <0.4 → >=1.0 | 18 |
| `cohere` | pypi | <5.0 → >=5.0 | 11 |
| `mistralai` | pypi | <1.0 → >=1.0 | 13 |
| `haystack-ai` | pypi | <2.0 → >=2.0 | 17 |
| `google-generativeai` | pypi | deprecated → `google-genai` | 11 |
| `google-cloud-aiplatform` | pypi | `vertexai.*` deprecated → `google-genai` | 17 |
| `@google/generative-ai` | npm | deprecated → `@google/genai` | 5 |
| `transformers` | pypi | 4.x → 5.x | 7 |
| `ai` (Vercel) | npm | 5.x → 6.x | 4 |
| `ai` (Vercel) | npm | 6.x → 7.x | 3 |
| `mcp` | pypi | 1.x → 2.x | 10 |

**Total: 244 documented breaking changes across 20 packages.**

## How to Use

### As a data source (for tools)

Fetch the generated JSON index:

```bash
curl -s https://raw.githubusercontent.com/onthedrops/ai-sdk-breakage-registry/main/generated/registry.json
```

Or install as a Python package (coming soon):

```bash
pip install ai-sdk-breakage-registry
```

### With devcheck-ai

```bash
devcheck-ai ./my-project --breaking-changes
```

When devcheck-ai detects major version drift, it checks this registry and reports:

```
HIGH  openai  pypi  0.28.0 → 3.1.0
  ⚠ Known breaking change: openai.ChatCompletion.create → client.chat.completions.create
  ⚠ Known breaking change: openai.api_key = "..." → OpenAI(api_key="...")
  ⚠ Known breaking change: openai.embeddings_utils removed
  📖 Migration guide: https://github.com/openai/openai-python/discussions/742
```

### Validate entries locally

```bash
pip install pyyaml pytest

# Deterministic checks (run on every PR)
python scripts/verify_registry.py           # structural + self-consistency + URL syntax
python scripts/build_registry.py --check    # verify registry.json is in sync
python -m pytest tests/ -v                  # run all tests

# Optional: verify source URLs are live (weekly CI + manual)
python scripts/verify_registry.py --check-urls
```

### Verification checks

The `verify_registry.py` script performs these deterministic checks:

- **YAML structure** — required fields exist on every entry and change
- **Regex compilation** — every detection pattern is valid Python regex
- **Self-consistency** — at least one detection regex matches the entry's own `before` code block
- **Symbol containment** — `symbol_before` / `symbol_after` tokens appear in their code blocks (warning, not error)
- **URL syntax** — every source URL is valid HTTP(S)
- **Duplicate detection** — no duplicate entries with the same symbol, type, and regex within a package
- **Registry sync** — `generated/registry.json` matches the YAML sources

### Content verification (`--check-content`)

Fetches all source URLs for each package, extracts readable text from the pages, builds a combined corpus, and verifies that key API terms from each change entry appear in the documentation. This catches content drift — pages that still return HTTP 200 but no longer mention the API they're cited for.

- **Term extraction** — pulls concrete API names (class names, method names, import paths, dotted symbols) from each entry's `symbol_before`, `symbol_after`, `before`/`after` code blocks, and detection regexes
- **Generic token filtering** — excludes common programming words like `client`, `model`, `result`, `import`, `from` that would match any page
- **GitHub raw conversion** — `github.com/.../blob/...` URLs are auto-converted to `raw.githubusercontent.com` for reliable text access
- **JS-rendered detection** — pages with minimal text or "enable JavaScript" messages are marked unverifiable (warning, not error)
- **Aggregate corpus** — all source URLs for a package are combined, so a blog post + migration guide + deprecation page together form the verification corpus
- **Rate-limited** — 300ms delay between URL fetches, 15s timeout, 2MB content cap

#### Latest content verification results

Last run: September 8, 2026 (structural); content verification pending for Wave 2 packages (ChromaDB, Cohere, Mistral, Haystack)

**Structural verification** (all 20 packages, 244 changes):

| Check | Result |
|-------|--------|
| Structural validation | 244 passed, 0 errors |
| Regex compilation | 608 passed, 0 errors |
| Self-consistency | 852 passed, 0 errors |
| Symbol containment | 1096 passed, 19 warnings (soft) |
| URL syntax | 1174 passed, 0 errors |
| Duplicate detection | 1194 passed, 0 errors |
| Registry JSON sync | OK (244 changes) |

**Content verification** (Wave 1 packages only — 113 changes verified against source docs):

| Metric | Result |
|--------|--------|
| Unique source URLs fetched | 29 |
| URLs returned valid content | 26 |
| JS-rendered pages (unverifiable) | 3 |
| Failed fetches | 0 |
| Changes verified against source docs | 104 / 113 (92%) |
| Changes unverifiable (warning) | 9 |
| Errors | 0 |

The 9 unverifiable changes are all from packages whose source documentation is JS-rendered (LangChain deprecation page, PyPI package pages) and therefore can't be text-matched automatically. The API terms being checked are correct — the pages just don't serve enough raw HTML for automated verification. These are tracked as warnings, not errors.

| Package | Changes | Verified | Unverifiable |
|---------|---------|----------|-------------|
| `openai` (pypi) | 7 | 6 | 1 (PyPI page is JS-rendered) |
| `langchain` (pypi) | 51 | 42 | 9 (deprecation page is JS-rendered) |
| `google-generativeai` (pypi) | 11 | 11 | 0 |
| `google-cloud-aiplatform` (pypi) | 17 | 17 | 0 |
| `transformers` (pypi) | 7 | 6 | 1 (PyPI page is JS-rendered) |
| `anthropic` (pypi) | 3 | 3 | 0 |
| `openai` (npm) | 5 | 5 | 0 |
| `ai` (Vercel v6) (npm) | 3 | 2 | 1 (deepwiki page is JS-rendered) |
| `ai` (Vercel v7) (npm) | 4 | 4 | 0 |
| `@google/generative-ai` (npm) | 5 | 5 | 0 |

### CI Workflow

The [verify-registry.yml](.github/workflows/verify-registry.yml) workflow runs:

- **On every push/PR**: deterministic checks + test suite + registry sync check
- **Weekly (Sundays)**: URL liveness + content verification (catches dead links and content drift)
- **Manual dispatch**: URL + content verification on demand

## Contributing

We need community help to cover more SDKs and version transitions.

### Adding a new entry

1. Pick a breaking change from an official changelog or migration guide
2. Create a YAML file in `data/pypi/` or `data/npm/`
3. Follow the [schema](schema/breaking-change.schema.json)
4. Include at least one official source URL
5. Include before/after code examples
6. Add detection regex patterns
7. Run `python tools/validate.py` to verify
8. Submit a PR using the [PR template](.github/PULL_REQUEST_TEMPLATE.md)

### SDKs we want help with

- `tiktoken` (encoding API changes)
- `langgraph` (major version changes)
- `qdrant-client` (major version changes)
- `sentence-transformers` (major version changes)
- Replicate Python SDK
- ElevenLabs SDK
- AssemblyAI SDK

### Quality standards

Every entry must have:
- At least one **official source URL** (changelog, migration guide, GitHub release)
- **Before/after code examples** that are syntactically correct
- **Detection patterns** that match old-style code
- A `last_verified` date no older than 6 months
- A `confidence` level (high = verified from official docs, medium = from community reports, low = inferred)

## Directory Structure

```
ai-sdk-breakage-registry/
├── schema/
│   └── breaking-change.schema.json   # JSON schema for entries
├── data/
│   ├── pypi/                         # Python package entries
│   │   ├── openai.yaml
│   │   ├── anthropic.yaml
│   │   ├── langchain.yaml            # v0.1 → v0.2 (51 changes)
│   │   ├── langchain-v03.yaml        # v0.2 → v1.0 (16 changes)
│   │   ├── llamaindex.yaml
│   │   ├── pinecone.yaml
│   │   ├── weaviate-client.yaml
│   │   ├── google-generativeai.yaml
│   │   ├── google-cloud-aiplatform.yaml
│   │   ├── transformers.yaml
│   │   ├── chromadb.yaml
│   │   ├── cohere.yaml
│   │   ├── mistralai.yaml
│   │   └── haystack-ai.yaml
│   └── npm/                          # Node.js package entries
│       ├── openai.yaml
│       ├── anthropic.yaml
│       ├── vercel-ai-sdk.yaml
│       └── vercel-ai-sdk-v7.yaml
├── generated/
│   └── registry.json                 # Built index for tool consumption
├── scripts/
│   ├── build_registry.py             # Registry builder + sync check
│   └── verify_registry.py            # Verification (deterministic + content)
├── tests/                            # Test suite (53 tests)
└── .github/
    ├── workflows/verify-registry.yml # CI pipeline
    └── PULL_REQUEST_TEMPLATE.md      # Contribution template
```

## License

MIT — see [LICENSE](LICENSE).
