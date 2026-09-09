# Tool-Using ReAct

`react` is for tasks where the model should choose and chain tools. It still
lives inside the behavior tree as one leaf.

```python
from jdsl import react, root, tool

@tool
def distance_km(origin: str, destination: str) -> int:
    """Road distance between two cities."""
    ...

@tool
def drive_hours(km: int) -> float:
    """Driving time in hours."""
    ...

@tool
def fuel_cost(km: int) -> float:
    """Fuel cost for the trip."""
    ...

skill = (
    root("Trip", system="Use tools for every number.")
    .model("deepseek-chat")
    .do(react("request -> answer", tools=[distance_km, drive_hours, fuel_cost], max_steps=8))
)
```

Run the example:

```bash
uv run jdsl run examples/trip.py \
  -i request="Driving Nairobi to Mombasa - how long and how much fuel?"
```

## Tool Schemas

`@tool` keeps the callable usable from Python and attaches metadata for the model.
`react` derives a JSON schema from the function signature:

| Python hint | Tool schema |
| --- | --- |
| `str` | `string` |
| `int` | `integer` |
| `float` | `number` |
| `bool` | `boolean` |
| `list[T]`, `tuple`, `set` | `array` |

Arguments without defaults are required. Unannotated arguments fall back to
strings.

## Failure and Recovery

If the model calls an unknown tool, jdsl sends an error observation back into the
loop. If a tool raises, jdsl also sends an error observation rather than crashing
the whole `react` leaf. The leaf fails only when no final answer arrives within
`max_steps` or the final answer is empty.

Use a selector outside `react` when you want a deterministic fallback:

```python
sel(
    react("request -> answer", tools=[search, fetch], max_steps=6),
    act(fallback_answer),
)
```
