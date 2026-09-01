# Refinement Loops

`repeat` lets a tree express bounded retry and revision.

```python
from jdsl import check, predict, repeat, root, sel, seq

skill = (
    root("Refine", system="One tight paragraph.")
    .model("deepseek-chat")
    .do(seq(
        predict("topic -> draft", instructions="Write one paragraph."),
        repeat(
            seq(
                predict(
                    "draft -> critique, ok",
                    instructions="Set ok to 'yes' if the draft is clear enough.",
                ),
                sel(
                    check("ok", "yes"),
                    predict("draft, critique -> draft", instructions="Revise the draft."),
                ),
            ),
            until=check("ok", "yes"),
            max=3,
        ),
    ))
)
```

Run the example:

```bash
uv run jdsl run examples/refine.py -i topic="why sourdough needs a starter"
```

## Loop Semantics

`repeat(child, until=guard, max=3)` is do-while:

1. run `child`
2. check `until`
3. stop if it succeeds
4. repeat until `max`

If the child fails, the repeat fails immediately. If `max` is reached and
`until` never passed, the repeat fails.

## Skip Work with a Selector

The inner selector avoids revising a good draft:

```python
sel(
    check("ok", "yes"),
    predict("draft, critique -> draft"),
)
```

When `ok` is yes, the selector succeeds at the guard and skips the revision
branch.
