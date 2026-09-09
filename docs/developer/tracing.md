# Tracing Model

The harness compiles behavior from canonical trace events. Runtime tracing is
optional; without a trace sink, the interpreter runs normally.

## Event Flow

When `RunContext.trace_sink` is set, nodes emit:

- `node.enter`
- `node.exit`
- `tool.call.started`
- `tool.call.completed`
- `tool.call.failed`
- `model.requested`
- `model.responded`
- `blackboard.write`
- `react.started`
- `toolset.exposed`
- `react.finished`

`TraceEvent` carries `capture_id`, `episode_id`, source metadata, parent linkage,
sequence number, and hash-chain fields.

## Episodes

`segment_episodes` groups ordered events by episode. The compiler normalizer
turns an episode into:

- ordered tool steps
- tool arguments
- tool results
- exact argument lineage against prior trusted state
- observed model decision slots
- success or reward outcome

## Fidelity

Capture fidelity is inferred from the events present:

| Level | Evidence |
| --- | --- |
| F0 | no useful behavioral events |
| F1 | messages only |
| F2 | tool calls |
| F3 | tool calls plus state snapshots or state deltas |
| F4 | tool calls, state, and model decision context |

Host hooks usually see tool events but not private model reasoning. Gateway or
jdsl-native capture gives the compiler more evidence.
