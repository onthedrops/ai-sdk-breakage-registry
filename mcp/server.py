"""MCP server exposing the AI SDK breakage registry.

Lets a coding agent check an API call against known breaking changes
*before* generating code, rather than discovering the break at runtime.

Run locally over stdio:
    python server.py
"""

from __future__ import annotations

import json
from typing import Annotated, Optional

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

import registry_query as rq

mcp = MCPServer("ai_sdk_breakage_mcp")

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


def _json(payload) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


@mcp.tool(
    name="sdk_breakage_check_symbol",
    title="Check an API symbol for known breakage",
    annotations=READ_ONLY,
)
def sdk_breakage_check_symbol(
    symbol: Annotated[
        str,
        Field(
            description=(
                "The API call or symbol about to be written, e.g. "
                "'openai.ChatCompletion.create' or 'client.completions.create'. "
                "A full line of code also works."
            ),
            min_length=1,
            max_length=500,
        ),
    ],
    package: Annotated[
        Optional[str],
        Field(
            default=None,
            description="Optional package name to disambiguate, e.g. 'openai'.",
        ),
    ] = None,
) -> str:
    """Check whether an API symbol has a known breaking change.

    Call this BEFORE writing code that uses an AI SDK. If the symbol is
    deprecated or removed, this returns the replacement, a migration note,
    and before/after examples. An empty result means no known breakage.

    Returns:
        JSON list of matching changes, most specific first.
    """
    registry = rq.load_registry()
    hits = rq.check_symbol(registry, symbol, package)
    if not hits:
        return _json(
            {
                "symbol": symbol,
                "known_breakage": False,
                "note": (
                    "No known breaking change for this symbol. The registry covers "
                    "19 package transitions; absence is not proof the symbol is current."
                ),
            }
        )
    return _json({"symbol": symbol, "known_breakage": True, "matches": hits})


@mcp.tool(
    name="sdk_breakage_get_package",
    title="Get all breaking changes for a package",
    annotations=READ_ONLY,
)
def sdk_breakage_get_package(
    package: Annotated[
        str,
        Field(description="Package name, e.g. 'langchain', 'openai'.", min_length=1),
    ],
    ecosystem: Annotated[
        Optional[str],
        Field(default=None, description="Filter by ecosystem: 'pypi' or 'npm'."),
    ] = None,
    include_examples: Annotated[
        bool,
        Field(
            default=False,
            description=(
                "Include before/after code for each change. Verbose -- leave false "
                "unless the migration examples are actually needed."
            ),
        ),
    ] = False,
) -> str:
    """List every documented breaking change for a package.

    Use when migrating a dependency, or to see what changed between versions.

    Returns:
        JSON list of registry entries with changes, sources, and verification dates.
    """
    registry = rq.load_registry()
    entries = rq.get_package(registry, package, ecosystem, include_examples)
    if not entries:
        available = sorted({e["package"] for e in rq.list_packages(registry)})
        return _json(
            {
                "package": package,
                "found": False,
                "error": f"No registry entry for '{package}'.",
                "available_packages": available,
            }
        )
    return _json({"package": package, "found": True, "entries": entries})


@mcp.tool(
    name="sdk_breakage_search",
    title="Search breaking changes by keyword",
    annotations=READ_ONLY,
)
def sdk_breakage_search(
    query: Annotated[
        str,
        Field(
            description=(
                "Keyword to search across summaries, symbols, and migration notes, "
                "e.g. 'streaming', 'embeddings', 'import path'."
            ),
            min_length=1,
        ),
    ],
    limit: Annotated[
        int, Field(default=20, description="Maximum results.", ge=1, le=100)
    ] = 20,
) -> str:
    """Search the registry when the exact symbol is unknown.

    Returns:
        JSON list of matching changes with package and replacement symbol.
    """
    registry = rq.load_registry()
    hits = rq.search(registry, query, limit)
    return _json({"query": query, "result_count": len(hits), "results": hits})


@mcp.tool(
    name="sdk_breakage_list_packages",
    title="List registry coverage",
    annotations=READ_ONLY,
)
def sdk_breakage_list_packages() -> str:
    """List every package covered by the registry, with counts and freshness.

    Use to check whether a package is covered before relying on a negative
    result from sdk_breakage_check_symbol.

    Returns:
        JSON list of covered packages with change counts and last_verified dates.
    """
    registry = rq.load_registry()
    rows = rq.list_packages(registry)
    return _json(
        {
            "entry_count": len(rows),
            "total_changes": registry.get("total_changes", 0),
            "packages": rows,
        }
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
