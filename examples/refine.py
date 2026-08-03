"""Iterative refinement: draft → critique → revise, until the critique passes.

The first `predict` drafts. Then a `repeat` loops a critique+revise body: each
pass critiques the current draft (setting `ok`), and — via an inner `sel` — skips
revision once it's good, otherwise rewrites the draft. `until=check("ok","yes")`
stops the loop; `max` bounds it. This needs the `repeat` primitive; the rest of
the tree couldn't express "keep going until good".

Run it:  uv run jdsl run examples/refine.py -i topic="why sourdough needs a starter"
"""

from jdsl import check, predict, repeat, root, sel, seq

skill = (
    root("Refine", system="You are a sharp writing editor. One tight paragraph, no fluff.")
    .model("deepseek-chat")
    .do(
        seq(
            predict("topic -> draft", instructions="Write one paragraph on the topic."),
            repeat(
                seq(
                    predict(
                        "draft -> critique, ok",
                        instructions="Critique the draft in one line. Be a lenient editor: set ok to exactly "
                                     "'yes' if it is clear and correct (perfection not required); use exactly "
                                     "'no' only for a concrete, significant flaw.",
                    ),
                    sel(
                        check("ok", "yes"),  # good enough → skip revision
                        predict("draft, critique -> draft", instructions="Rewrite the draft addressing the critique."),
                    ),
                ),
                until=check("ok", "yes"),
                max=3,
            ),
        )
    )
)


if __name__ == "__main__":
    ctx = skill.run(topic="why sourdough bread needs a starter")
    print("ok      :", ctx.blackboard.get("ok"))
    print("critique:", ctx.blackboard.get("critique"))
    print("draft   :", (ctx.blackboard.get("draft") or "")[:300])
