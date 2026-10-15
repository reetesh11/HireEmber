"""Rename AC-11: README install and command examples use `hireember`."""

from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"
OLD = "apply" + "pilot"


def test_readme_title_is_hireember():
    lines = [line.rstrip() for line in README.read_text(encoding="utf-8").splitlines()]
    titles = [line for line in lines if line.startswith("# ")]
    assert titles and titles[0] == "# HireEmber", titles


def test_readme_install_and_command_examples_use_hireember():
    text = README.read_text(encoding="utf-8")
    for example in (
        "pip install hireember",
        "hireember init",
        "hireember doctor",
        "hireember run",
        "hireember apply",
        "hireember status",
        "hireember dashboard",
    ):
        assert example in text, f"README is missing {example!r}"
    for old in ("pip install " + OLD, OLD + " init", OLD + " run", OLD + " apply", OLD + " doctor",
                OLD + " status", OLD + " dashboard"):
        assert old not in text, f"README still says {old!r}"
