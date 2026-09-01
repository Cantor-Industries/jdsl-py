# Publishing

The documentation is a MkDocs site using the built-in `readthedocs` theme.

```bash
uv run --group docs mkdocs build --strict
```

The build output is `site/`, which is ignored by Git. Do not commit generated
HTML.

`use_directory_urls` is disabled, so subpages are emitted as explicit files such
as `quickstart.html` and `compiler.html`. This avoids relying on directory index
handling for project-page subpaths.

## GitHub Pages

The workflow at `.github/workflows/docs.yml` builds the site and deploys the
generated `site/` directory with GitHub's Pages artifact actions:

1. `actions/configure-pages`
2. `actions/upload-pages-artifact`
3. `actions/deploy-pages`

Repository settings must use GitHub Actions as the Pages source:

```text
Settings -> Pages -> Build and deployment -> Source -> GitHub Actions
```

If the source is set to `Deploy from a branch` and points at `/docs`, GitHub
Pages serves the Markdown source directory rather than the generated MkDocs site.
That commonly produces a 404 at the project root because the deployed source
does not contain the expected generated `index.html`.

After a successful deploy, use the URL shown by the `deploy` job environment.
For this repository the configured project URL is:

```text
https://cantor-industries.github.io/jdsl-py/
```

## Private Drafts

Design notes, roadmap docs, and experiment notebooks live under `docs/drafts/`.
That directory is ignored and excluded from MkDocs. Public pages should summarize
implemented behavior and link only to tracked documentation.
