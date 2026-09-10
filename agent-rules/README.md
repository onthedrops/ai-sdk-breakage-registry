# Agent rules

The MCP server only helps if the agent actually calls it. These files tell it
when to, and how to read the answer.

[`AGENTS.md`](AGENTS.md) is the rule text. Install it with whichever convention
your tool uses:

| Tool | Where it goes |
| --- | --- |
| Claude Code | Append to your project's `CLAUDE.md` |
| Cursor | Append to `.cursorrules`, or add as a project rule |
| GitHub Copilot | Append to `.github/copilot-instructions.md` |
| Anything reading `AGENTS.md` | Copy to the repo root |

Install the MCP server first — see [`../mcp/README.md`](../mcp/README.md). The
rule references its tool names, so without the server the agent will follow the
instruction and find nothing to call.

## Why a rule is needed

Nothing makes a model consult a tool it was not told to consult. Left to
itself, a coding agent writes the API call it learned during training, which
for these packages is frequently the removed one. The rule converts the server
from something available into something used.
