"""CLI surface via typer's test runner."""

from __future__ import annotations

from typer.testing import CliRunner

from jdsl.cli import app

runner = CliRunner()


def test_config_add_then_list_masks_keys(isolated_config):
    r = runner.invoke(app, ["config", "add", "-p", "deepseek", "sk-abcdefgh1234"])
    assert r.exit_code == 0

    r2 = runner.invoke(app, ["config", "list"])
    assert r2.exit_code == 0
    assert "deepseek" in r2.output
    assert "sk-abcdefgh1234" not in r2.output  # masked, not printed in full


def test_config_add_unknown_provider_exits_nonzero(isolated_config):
    r = runner.invoke(app, ["config", "add", "-p", "nope", "x"])
    assert r.exit_code == 1


def test_config_list_empty(isolated_config):
    r = runner.invoke(app, ["config", "list"])
    assert r.exit_code == 0
    assert "No stored credentials" in r.output


def test_run_deterministic_skill(tmp_path):
    f = tmp_path / "s.py"
    f.write_text(
        "from jdsl import act, root, seq, store\n"
        'skill = root("Echo").do(seq(store(act(lambda: "hi"), "msg")))\n'
    )
    r = runner.invoke(app, ["run", str(f)])
    assert r.exit_code == 0
    assert "Echo" in r.output and "hi" in r.output


def test_run_seeds_inputs_with_flag(tmp_path):
    f = tmp_path / "s.py"
    f.write_text(
        "from jdsl import act, ref, root, seq, store\n"
        'skill = root("Up").do(seq(store(act(lambda x: x.upper(), ref("word")), "out")))\n'
    )
    r = runner.invoke(app, ["run", str(f), "-i", "word=hello"])
    assert r.exit_code == 0
    assert "HELLO" in r.output


def test_run_bad_input_format_errors(tmp_path):
    f = tmp_path / "s.py"
    f.write_text('from jdsl import root, seq\nskill = root("X").do(seq())\n')
    r = runner.invoke(app, ["run", str(f), "-i", "noequals"])
    assert r.exit_code != 0


def test_run_file_without_skills_exits_nonzero(tmp_path):
    f = tmp_path / "empty.py"
    f.write_text("x = 1\n")
    r = runner.invoke(app, ["run", str(f)])
    assert r.exit_code == 1
