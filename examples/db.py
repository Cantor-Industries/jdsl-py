"""A ReAct agent that explores an unknown in-memory database, then aggregates.

Robustness angle: the model is told *nothing* about the schema, so it can't
shortcut — it must discover tables, inspect columns, query the right rows, then
reduce them with a tool. `mean` takes a `list[float]`, which shows react handing
the model a tool whose argument is a JSON array (schema derived from the type
hint), not just scalars.

Run it:
  uv run jdsl run examples/db.py -i question="What is the average salary in the Engineering department?"
"""

from jdsl import react, root, tool

_DB = {
    "employees": [
        {"name": "Alice", "dept": "Engineering", "salary": 120000},
        {"name": "Bob", "dept": "Engineering", "salary": 140000},
        {"name": "Carol", "dept": "Sales", "salary": 90000},
        {"name": "Dave", "dept": "Engineering", "salary": 100000},
        {"name": "Eve", "dept": "Sales", "salary": 95000},
    ],
    "departments": [
        {"name": "Engineering", "floor": 3},
        {"name": "Sales", "floor": 1},
    ],
}


@tool
def tables() -> list[str]:
    """List the tables in the database."""
    return list(_DB)


@tool
def schema(table: str) -> list[str]:
    """Column names of a table."""
    return list(_DB[table][0].keys()) if _DB.get(table) else []


@tool
def query(table: str, column: str, equals: str) -> list[dict]:
    """Rows of `table` where `column` == `equals` (string-compared)."""
    return [row for row in _DB.get(table, []) if str(row.get(column)) == equals]


@tool
def mean(numbers: list[float]) -> float:
    """Arithmetic mean of a list of numbers."""
    return round(sum(numbers) / len(numbers), 2) if numbers else 0.0


skill = (
    root("DB", system="You are a data analyst. Discover the schema with tools before querying. "
                     "Compute aggregates with tools, not by guessing.")
    .model("deepseek-chat")
    .do(react("question -> answer", tools=[tables, schema, query, mean], max_steps=12))
)


if __name__ == "__main__":
    ctx = skill.run(question="What is the average salary in the Engineering department?")
    print("answer:", ctx.blackboard.get("answer"))
    # expected: (120000 + 140000 + 100000) / 3 = 120000
