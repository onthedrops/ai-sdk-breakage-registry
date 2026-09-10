# AI SDK breakage check

When writing or editing code that calls an AI SDK, check the call against the
breakage registry **before** writing it, not after it fails.

## When this applies

Any code touching these packages:

`openai`, `anthropic`, `langchain`, `llamaindex`, `mcp`, `cohere`, `mistralai`,
`chromadb`, `pinecone`, `weaviate-client`, `haystack-ai`, `transformers`,
`google-generativeai`, `google-cloud-aiplatform`, and the Vercel `ai` package.

These SDKs have had major breaking releases recently enough that model training
data commonly contains their removed APIs. A call that looks correct may target
a version that no longer exists.

## What to do

1. Before emitting the call, run `sdk_breakage_check_symbol` with the exact
   symbol or the whole line, e.g. `openai.ChatCompletion.create`.
2. If `known_breakage` is true, write `symbol_after` instead and follow
   `migration_note`. The `before` and `after` fields show working code.
3. If you are migrating a dependency rather than writing one call, use
   `sdk_breakage_get_package` for the full change list.

## How to read an empty result

An empty result means **no documented breakage for that symbol**. It is not
evidence that the symbol is current. The registry covers a specific set of
version transitions; anything outside that set returns nothing regardless of
whether it still works.

Before treating an empty result as reassurance, call
`sdk_breakage_list_packages` to see what is actually covered. If the package is
not in that list, the check told you nothing and you should verify against the
vendor's own documentation.

## What not to do

- Do not invent a migration. If the registry has no entry, say so.
- Do not present a registry entry as current fact without its `last_verified`
  date when the user is relying on it for a decision.
- Do not skip the check because the code "looks fine". Looking fine is exactly
  the failure mode: these APIs were valid, which is why they are in the
  training data.
