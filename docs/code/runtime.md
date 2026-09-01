# Runtime Interpreter

The interpreter lives in [`jdsl/tree.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/tree.py).
Every node implements `_tick(ctx) -> Status`. The public `tick(ctx)` wrapper adds
trace events when tracing is enabled.

## Run Entry

`Root.run(...)` creates a `RunContext`:

```python
ctx = RunContext(
    blackboard=Blackboard(inputs),
    model=model,
    model_id=self.model_id,
    trace_sink=trace_sink,
    capture_id=capture_id,
    episode_id=episode_id,
)
```

If the root has a model id and no explicit model object was passed,
`LanguageModel.from_config()` is used. If a trace sink is present, runtime node
ids are assigned and episode events are emitted.

## Status

Only two statuses exist:

```python
Status.SUCCESS
Status.FAILURE
```

`Status.SUCCESS` is truthy. A tool can return `Status.FAILURE` to let a parent
selector recover without raising an exception.

## Composites

`Sequence` is behavior-tree AND:

```text
for child in children:
  if child fails:
    return FAILURE
return SUCCESS
```

`Selector` is behavior-tree OR:

```text
for child in children:
  if child succeeds:
    return SUCCESS
return FAILURE
```

These two nodes are enough to express most routing: `predict` writes a field,
then `sel(seq(check(...), act(...)), fallback)` consumes it.

## Actions

`Action._tick` resolves all refs, emits a tool-call start event if tracing is
enabled, calls the function, then emits a completion or failure event.

Return handling:

- exception: trace failure, then re-raise
- `Status`: return it directly
- any other value: succeed; store it if `store_as` is set

The blackboard write uses the action label as provenance:

```text
act(search_titles) -> titles
```

## Predict

`Predict` is a stateless one-shot model call. It reads declared input fields from
the blackboard and sends one user message. It does not append earlier assistant
output to the next model call.

Single output:

```text
question -> answer
```

The model's stripped text is written directly to `answer`.

Multiple outputs:

```text
ticket -> category, urgency
```

The model is asked for a JSON object and each key is written separately. If JSON
cannot be parsed, the leaf returns `FAILURE`.

Compiled signatures may attach output schemas. In that case `Predict._coerce`
validates/coerces values before writing them.

## React

`React` is a model-driven tool loop inside one leaf.

1. derive JSON schemas from the provided `@tool` functions
2. ask the model for a tool call or final answer
3. run requested tools
4. feed tool results back to the model
5. stop when a final answer arrives or `max_steps` is hit

Unknown tools and tool exceptions become error observations inside the loop.
The leaf fails if no final answer arrives.

## Scoped Context

Every node can have `context=...`. `Node._run_with_context` pushes that text onto
the `ContextWindow` for the subtree and pops it afterward. The model sees the
joined stack as the system prompt.

This lets a root set task-wide policy and a leaf or subtree add local policy
without permanently contaminating later leaves.

## Runtime State

`RunContext` is defined in [`jdsl/context.py`](https://github.com/Cantor-Industries/jdsl-py/blob/harness/jdsl/context.py).
It carries:

- `blackboard`: shared values and write provenance
- `window`: scoped system context
- `model` and `model_id`
- `state`: per-run scratch, used by `oneshot`
- trace fields: sink, capture id, episode id, event source
