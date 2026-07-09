# Allowed Tools

skill-cert agent is allowed to use the following tool categories:

## Read & Write
- **read**: Read file contents
- **write**: Write or create files
- **edit**: Edit existing files (preferred over write for existing files)

## Search
- **glob**: Find files by pattern
- **grep**: Search file contents by regex

## Execution
- **bash**: Execute shell commands (read-only operations preferred; destructive commands require confirmation)

## Task Dispatch
- **task** (subagent delegation): Dispatch background explore/librarian agents for parallel research

## Dangerous Tool Restrictions

The following are **NOT allowed** without explicit user confirmation:
- Destructive shell commands (`rm -rf`, `DROP TABLE`, `force-push`, `git reset --hard`, `kubectl delete`)
- Network-dependent tools for non-read-only operations
- Modification of eval cases after Phase 2 execution begins

## MCP Tools (if available)
- `codegraph_*`: Code intelligence over indexed knowledge graph
- `context7_*`: Up-to-date library documentation
- `semble_*`: Semantic code search
- `skill_mcp`: MCP server operations from skill-embedded MCPs
