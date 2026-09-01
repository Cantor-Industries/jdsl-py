import type { Plugin } from "@opencode-ai/plugin"

const SCHEMA = "jdsl.opencode-hook.v1"

let warned = false

function env(name: string, fallback: string): string {
  const g = globalThis as unknown as {
    Bun?: { env?: Record<string, string | undefined> }
    process?: { env?: Record<string, string | undefined> }
  }
  return g.Bun?.env?.[name] ?? g.process?.env?.[name] ?? fallback
}

function endpoint(): string {
  const base = env("JDSL_INGEST_URL", "http://127.0.0.1:8848").replace(/\/$/, "")
  const cap = encodeURIComponent(env("JDSL_CAPTURE_ID", "cap_opencode"))
  return `${base}/hook/opencode?cap=${cap}`
}

async function forward(payload: Record<string, unknown>): Promise<void> {
  const timeout = Math.max(1, Number(env("JDSL_HOOK_TIMEOUT", "0.5")) * 1000)
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    await fetch(endpoint(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
  } catch (err) {
    if (!warned) {
      warned = true
      console.warn(`[jdsl] OpenCode hook capture unavailable: ${String(err)}`)
    }
  } finally {
    clearTimeout(timer)
  }
}

function now(): string {
  return new Date().toISOString()
}

function sessionID(input: Record<string, unknown>): string {
  return String(input.sessionID ?? input.session_id ?? input.sessionId ?? "opencode-session")
}

function callID(input: Record<string, unknown>): string | undefined {
  const value = input.callID ?? input.call_id ?? input.toolCallID ?? input.tool_call_id
  return value == null ? undefined : String(value)
}

export const JdslHarness: Plugin = async ({ directory, worktree }) => {
  return {
    event: async ({ event }) => {
      const item = event as Record<string, unknown>
      const type = String(item.type ?? "")
      if (!type.startsWith("session.")) return
      await forward({
        schema: SCHEMA,
        hook: type,
        session_id: sessionID(item),
        error: item.error,
        status: item.status,
        directory,
        worktree,
        timestamp: now(),
      })
    },

    "tool.execute.before": async (input, output) => {
      await forward({
        schema: SCHEMA,
        hook: "tool.execute.before",
        session_id: sessionID(input as Record<string, unknown>),
        call_id: callID(input as Record<string, unknown>),
        tool: String(input.tool),
        args: output.args ?? {},
        directory,
        worktree,
        timestamp: now(),
      })
    },

    "tool.execute.after": async (input, output) => {
      await forward({
        schema: SCHEMA,
        hook: "tool.execute.after",
        session_id: sessionID(input as Record<string, unknown>),
        call_id: callID(input as Record<string, unknown>),
        tool: String(input.tool),
        result: {
          title: output.title,
          output: output.output,
          metadata: output.metadata,
        },
        directory,
        worktree,
        timestamp: now(),
      })
    },
  }
}
