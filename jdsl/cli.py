"""The jdsl CLI: `config add`, `config list`, `run <file>`."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import typer

from jdsl import config
from jdsl.tree import Root

app = typer.Typer(add_completion=False, help="Declarative behavior-tree agents over Claude.")
config_app = typer.Typer(help="Manage provider API keys (~/.local/share/recon/auth.json).")
app.add_typer(config_app, name="config")


@config_app.command("add")
def config_add(
    keys: list[str] = typer.Argument(..., help="One or more API keys to store."),
    provider: str = typer.Option("anthropic", "-p", "--provider", help="Provider name."),
) -> None:
    """Store API keys for a provider (de-duplicated, merged)."""
    try:
        merged = config.add_keys(provider, keys)
    except ValueError as err:
        typer.secho(str(err), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from None
    typer.secho(
        f"Stored {len(keys)} key(s) for {provider!r} ({len(merged)} total) at {config.auth_path()}.",
        fg=typer.colors.GREEN,
    )


@config_app.command("list")
def config_list() -> None:
    """Print the current auth config with keys masked."""
    current = config.load()
    if not current:
        typer.echo("No stored credentials.")
        return
    for provider, entry in current.items():
        typer.secho(provider, fg=typer.colors.CYAN, bold=True)
        for key in entry.get("api_keys", []):
            typer.echo(f"  {_mask(key)}")


@app.command("run")
def run(
    file: Path = typer.Argument(..., exists=True, readable=True, help="A .py file defining skills."),
    inputs: list[str] = typer.Option(
        [], "-i", "--input", help="Seed a blackboard input as key=value (repeatable)."
    ),
) -> None:
    """Import ``file`` and execute every ``root()`` skill defined at module level."""
    seed = dict(_parse_kv(item) for item in inputs)
    module = _load_module(file)
    roots = [v for v in vars(module).values() if isinstance(v, Root)]
    if not roots:
        typer.secho(f"No skills (root(...)) found in {file}.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    for skill in roots:
        typer.secho(f"▶ running {skill.name!r}", fg=typer.colors.CYAN, bold=True)
        ctx = skill.run(**seed)
        if ctx.blackboard:
            typer.echo(f"  blackboard: {dict(ctx.blackboard)}")


def _parse_kv(item: str) -> tuple[str, str]:
    if "=" not in item: raise typer.BadParameter(f"--input must be key=value, got {item!r}.")
    key, value = item.split("=", 1)
    return key.strip(), value


def _load_module(file: Path):
    spec = importlib.util.spec_from_file_location(file.stem, file)
    if spec is None or spec.loader is None: raise typer.BadParameter(f"Cannot import {file}.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _mask(key: str) -> str:
    return "*" * len(key) if len(key) <= 8 else f"{key[:4]}…{key[-4:]}"


if __name__ == "__main__":  # pragma: no cover
    app()
