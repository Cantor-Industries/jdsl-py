"""The jdsl CLI: runtime (`config`, `run`, `show`) plus the harness/compiler
control surface (`capture`, `compile`, `package`, `harness`) from design §37.

Harness commands import `jdsl_harness` lazily, so the dependency-light runtime core
keeps working when the harness extra is not installed."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import typer

from jdsl import config
from jdsl.render import render
from jdsl.tree import Root

app = typer.Typer(add_completion=False, help="Declarative behavior-tree agents over Claude.")
config_app = typer.Typer(help="Manage provider API keys (~/.local/share/recon/auth.json).")
app.add_typer(config_app, name="config")

package_app = typer.Typer(help="Inspect, verify, and run compiled .jdslpkg behavior packages.")
capture_app = typer.Typer(help="List and inspect captured trace sets.")
harness_app = typer.Typer(help="Run the local harness daemon (ingest + control plane).")
app.add_typer(package_app, name="package")
app.add_typer(capture_app, name="capture")
app.add_typer(harness_app, name="harness")


def _store_root() -> Path:
    """Where the harness keeps its store; overridable via JDSL_HARNESS_HOME."""
    return Path(os.environ.get("JDSL_HARNESS_HOME") or (Path.home() / ".local/share/jdsl-harness"))


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
        for w in ctx.blackboard.clobbers():
            typer.secho(f"  ⚠ {w.key!r} overwritten by {w.writer} (was set by another node)",
                        fg=typer.colors.YELLOW)


@app.command("show")
def show(file: Path = typer.Argument(..., exists=True, readable=True, help="A .py file defining skills.")) -> None:
    """Print each skill's structure as an ASCII tree (no execution, no model)."""
    module = _load_module(file)
    roots = [v for v in vars(module).values() if isinstance(v, Root)]
    if not roots:
        typer.secho(f"No skills (root(...)) found in {file}.", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    for skill in roots:
        typer.echo(render(skill))


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


# -- package commands (§37) ---------------------------------------------------

@package_app.command("inspect")
def package_inspect(path: Path = typer.Argument(..., exists=True, help="A .jdslpkg or package dir.")) -> None:
    """Show a package's manifest, capabilities, and burden metrics."""
    from jdsl.package import load_package
    pkg = load_package(path)
    m = pkg.manifest
    typer.secho(f"{m.name} v{m.version}  [{m.format}]", fg=typer.colors.CYAN, bold=True)
    typer.echo(f"  task family: {m.task_family or 'n/a'}")
    typer.echo(f"  verification: {m.verification.get('status', 'unverified')} "
               f"(replay coverage {m.verification.get('replay_coverage', 'n/a')})")
    typer.echo(f"  fidelity: {m.source.get('capture_fidelity', 'n/a')}, "
               f"episodes: {m.source.get('episode_count', 'n/a')}")
    perms = pkg.permissions()
    typer.secho("  reads:  " + (", ".join(perms["reads"]) or "(none)"), fg=typer.colors.GREEN)
    typer.secho("  writes: " + (", ".join(perms["writes"]) or "(none)"),
                fg=typer.colors.RED if perms["writes"] else typer.colors.GREEN)


@package_app.command("verify")
def package_verify(path: Path = typer.Argument(..., exists=True, help="A .jdslpkg or package dir.")) -> None:
    """Structurally verify a package and its digests; exit non-zero on failure."""
    from jdsl.package import PackageError, load_package
    try:
        load_package(path)  # load_package runs digest + structural verification
    except PackageError as err:
        typer.secho(f"✗ invalid package: {err}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from None
    typer.secho("✓ package is structurally valid and digests match.", fg=typer.colors.GREEN)


@package_app.command("run")
def package_run(
    path: Path = typer.Argument(..., exists=True, help="A .jdslpkg or package dir."),
    tools: Path = typer.Option(..., "-t", "--tools", exists=True,
                               help="A .py file exposing TOOLS (dict) and optional PREDICATES."),
    model: str = typer.Option(None, "-m", "--model", help="Model id for residual leaves."),
    inputs: list[str] = typer.Option([], "-i", "--input", help="Seed blackboard key=value."),
) -> None:
    """Bind a package to host tools and run it with a (small) model."""
    from jdsl.package import load_package
    pkg = load_package(path)
    mod = _load_module(tools)
    tool_map = getattr(mod, "TOOLS", None)
    if not isinstance(tool_map, dict):
        typer.secho(f"{tools} must define a TOOLS dict (logical_id -> callable).", fg=typer.colors.RED)
        raise typer.Exit(1)
    predicates = getattr(mod, "PREDICATES", {})
    seed = dict(_parse_kv(item) for item in inputs)
    root = pkg.as_root(tool_map, predicates, model_id=model)
    ctx = root.run(**seed)
    typer.echo(f"  blackboard: {dict(ctx.blackboard)}")


# -- capture commands (§37) ---------------------------------------------------

@capture_app.command("list")
def capture_list() -> None:
    """List captures in the local harness store."""
    from jdsl_harness.store import HarnessStore
    for c in HarnessStore(_store_root()).list_captures():
        typer.echo(f"{c['capture_id']}  {c['status']:9} episodes={c['episodes']}  {c.get('note','')}")


@capture_app.command("inspect")
def capture_inspect(capture_id: str = typer.Argument(..., help="Capture id.")) -> None:
    """Print the exact-lineage report for a capture (§51)."""
    from jdsl_harness.capture import CaptureCoordinator
    from jdsl_harness.store import HarnessStore
    coord = CaptureCoordinator(HarnessStore(_store_root()))
    typer.echo(json.dumps(coord.lineage_report(capture_id), indent=2, default=str))


@app.command("compile")
def compile_cmd(
    capture_id: str = typer.Argument(..., help="Capture id to compile."),
    name: str = typer.Option("behavior", "-n", "--name", help="Package name."),
    out: Path = typer.Option(None, "-o", "--out", help="Write a .jdslpkg to this path."),
) -> None:
    """Compile a capture into a verified behavior package (§24)."""
    from jdsl.package import export_jdslpkg, package_digest
    from jdsl_harness.compiler import compile_behavior
    from jdsl_harness.store import HarnessStore
    store = HarnessStore(_store_root())
    result = compile_behavior(store.capture_episodes(capture_id), name=name)
    typer.echo(json.dumps(result.report(), indent=2, default=str))
    if out is not None:
        path = export_jdslpkg(result.package, out)
        store.record_package(name, result.package.manifest.version, package_digest(result.package),
                             status="built", path=str(path))
        typer.secho(f"→ wrote {path}", fg=typer.colors.GREEN)


# -- harness daemon (§37) -----------------------------------------------------

@harness_app.command("serve")
def harness_serve(
    host: str = typer.Option("127.0.0.1", help="Bind host (loopback by default)."),
    port: int = typer.Option(8848, help="Ingest port."),
) -> None:
    """Run the local ingest server (data plane). Ctrl-C to stop."""
    from jdsl_harness.server import IngestServer
    from jdsl_harness.store import HarnessStore
    server = IngestServer(HarnessStore(_store_root()), host=host, port=port).start()
    typer.secho(f"jdsl harness ingest listening on {server.url} (store: {_store_root()})",
                fg=typer.colors.CYAN)
    try:
        import time
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
        typer.echo("stopped.")


if __name__ == "__main__":  # pragma: no cover
    app()
