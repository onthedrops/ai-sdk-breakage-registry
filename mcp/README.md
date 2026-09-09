# AI SDK Breakage MCP Server

Exposes the registry to coding agents so they can check an API call against
known breaking changes **before** generating code, instead of discovering the
break at runtime.

## Tools

| Tool | Use |
| --- | --- |
| `sdk_breakage_check_symbol` | Check one symbol or line of code (`openai.ChatCompletion.create`) for known breakage. The main pre-generation check. |
| `sdk_breakage_get_package` | Every documented change for a package. Set `include_examples` for before/after code. |
| `sdk_breakage_search` | Keyword search when the exact symbol is unknown. |
| `sdk_breakage_list_packages` | Registry coverage with change counts and `last_verified` dates. |

All tools are read-only.

## Install

```bash
pip install -r mcp/requirements.txt
```

## Configure

Claude Desktop (`claude_desktop_config.json`) or any stdio MCP client:

```json
{
  "mcpServers": {
    "ai-sdk-breakage": {
      "command": "python",
      "args": ["/absolute/path/to/ai-sdk-breakage-registry/mcp/server.py"]
    }
  }
}
```

## Data source

The server reads `generated/registry.json` from this repository when run from a
checkout. Outside a checkout it falls back to a cached download of the published
JSON, refreshed every 7 days. Set `AI_SDK_BREAKAGE_CACHE_DIR` to relocate the cache.

## Coverage caveat

An empty result from `sdk_breakage_check_symbol` means *no known breakage*, not
*the symbol is current*. Call `sdk_breakage_list_packages` to see what is
actually covered before treating a negative as authoritative.

## Tests

```bash
pytest mcp/test_registry_query.py -q
```

The query layer has no MCP dependency, so the tests run without the SDK installed.
