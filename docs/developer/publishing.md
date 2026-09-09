# Publishing

The documentation is a MkDocs site using `mkdocs-material`, configured in the
same style as tinygrad's docs: Material navigation features, source-rendered
`mkdocstrings` reference pages, and richer Python Markdown extensions.

```bash
uv run --group docs mkdocs build --strict
```

The build output is `site/`, which is ignored by Git. Do not commit generated
HTML.

The site uses MkDocs' default directory URLs, matching tinygrad's docs. Subpages
are emitted as directories with `index.html` files, such as
`quickstart/index.html` and `code/compiler/index.html`, and should be visited as
`/quickstart/` and `/code/compiler/`.

The workflow also writes `site/.nojekyll` before upload. That keeps GitHub Pages
from applying Jekyll rules to the built static artifact and is especially useful
for generated theme/plugin assets.

## GitHub Pages

The workflow at `.github/workflows/docs.yml` follows the same publishing model
as tinygrad: it builds the Material site and runs `mkdocs gh-deploy --force`.
That command publishes the generated `site/` tree to the `gh-pages` branch.

`mkdocs gh-deploy` also writes the `.nojekyll` marker that keeps GitHub Pages
from processing generated assets through Jekyll.

Repository settings must serve the generated branch:

```text
Settings -> Pages -> Build and deployment
Source: Deploy from a branch
Branch: gh-pages
Folder: / (root)
```

Do not point Pages at the tracked `/docs` directory. That makes GitHub run
Jekyll over the Markdown source. The live page will look unthemed and its HTML
will include `generator: Jekyll` instead of `mkdocs-material`.

After a successful deploy, use the URL shown by the `deploy` job environment.
For this repository the configured project URL is:

```text
https://cantor-industries.github.io/jdsl-py/
```

## Private Drafts

Design notes, roadmap docs, and experiment notebooks live under `docs/drafts/`.
That directory is ignored and excluded from MkDocs. Public pages should summarize
implemented behavior and link only to tracked documentation.
