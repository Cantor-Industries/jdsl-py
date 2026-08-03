"""The README example, ported. Deterministic, no LLM.

Run it:  jdsl run examples/greeter.py
"""

from jdsl import act, root, seq, tool


@tool
def greet(name: str) -> None:
    print(f"hello {name}")


skill = (
    root("Greeter", system="You are a friendly greeter.")
    .do(seq(act(greet, "John")))
)


if __name__ == "__main__":
    skill.run()
