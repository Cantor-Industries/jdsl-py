"""Wikipedia lookup: search → let the model pick the best title → fetch content.

Shows how a tool argument is wired to a runtime value with ``ref``:
``ref("query")`` resolves the seeded input, ``ref("selected_title")`` resolves
the ``predict`` leaf's output.

Uses the Wikipedia API directly over httpx with a descriptive User-Agent (per
Wikimedia's policy) — reliable, unlike the unmaintained ``wikipedia`` package.

Run it:  uv run jdsl run examples/wiki.py -i query="Ada Lovelace"
"""

import httpx

from jdsl import act, predict, ref, root, seq, store, tool

_API = "https://en.wikipedia.org/w/api.php"
_HTTP = httpx.Client(
    headers={"User-Agent": "jdsl-example/0.1 (behavior-tree agent demo)"},
    timeout=15,
)


@tool
def search_titles(query: str) -> list[str]:
    resp = _HTTP.get(
        _API,
        params={"action": "opensearch", "search": query, "limit": 5, "format": "json"},
    )
    resp.raise_for_status()
    return resp.json()[1]  # opensearch returns [query, [titles], [descs], [urls]]


@tool
def fetch_content(title: str) -> str:
    resp = _HTTP.get(
        _API,
        params={
            "action": "query",
            "prop": "extracts",
            "explaintext": 1,
            "titles": title,
            "format": "json",
            "redirects": 1,
        },
    )
    resp.raise_for_status()
    pages = resp.json()["query"]["pages"]
    return next(iter(pages.values())).get("extract", "")


skill = (
    root(
        "Wikipedia Search",
        system="You retrieve information from Wikipedia.",
    )
    .model("deepseek-chat")  # or "claude-opus-4-8" — provider is inferred from the id
    .do(
        seq(
            store(act(search_titles, ref("query")), "titles"),
            predict(
                "titles -> selected_title",
                instructions="Pick the single most relevant title from the list, verbatim.",
            ),
            store(act(fetch_content, ref("selected_title")), "content"),
        )
    )
)


if __name__ == "__main__":
    ctx = skill.run(query="Python programming language")
    print("Selected title:", ctx.blackboard.get("selected_title"))
    content = ctx.blackboard.get("content") or ""
    print("Content:", content[:300], "…")
