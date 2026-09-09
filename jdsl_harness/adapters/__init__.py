"""Host + import adapters: translate host hooks and foreign logs into the one
canonical jdsl event schema (design §8.2, §8.3, §29)."""

from jdsl_harness.adapters import claude_code, gemini_cli, generic_mcp, import_jsonl, opencode

__all__ = ["claude_code", "gemini_cli", "generic_mcp", "import_jsonl", "opencode"]
