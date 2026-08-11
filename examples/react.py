"""ReAct: the model reasons and calls tools in a loop until it can answer.

Unlike `predict` (one shot, no tools), `react` lets the model pick and call the
`@tool`s itself via native function-calling, feeding each result back. This task
needs *chaining* — capital → population → arithmetic — which no single tool and
no single `predict` can do. The tree stays deterministic; the agentic loop is the
one `react` leaf.

Run it:  uv run jdsl run examples/react.py -i question="What is twice the population of the capital of France?"
"""

from jdsl import react, root, tool

_CAPITALS = {"france": "Paris", "japan": "Tokyo", "kenya": "Nairobi"}
_POPULATION = {"Paris": 2_100_000, "Tokyo": 14_000_000, "Nairobi": 4_400_000}


@tool
def capital_of(country: str) -> str:
    """The capital city of a country."""
    return _CAPITALS.get(country.strip().lower(), "unknown")


@tool
def population(city: str) -> int:
    """The population of a city."""
    return _POPULATION.get(city.strip().title(), 0)


@tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b


skill = (
    root("Agent", system="You are a precise research agent. Use tools; do not guess numbers.")
    .model("deepseek-chat")
    .do(react("question -> answer", tools=[capital_of, population, multiply], max_steps=6))
)


if __name__ == "__main__":
    ctx = skill.run(question="What is twice the population of the capital of Nairobi?")
    print("answer:", ctx.blackboard.get("answer"))
