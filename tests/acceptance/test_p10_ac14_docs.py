"""Phase 10 AC-14: README, CLI reference, traceability and CLI help mention adding jobs by URL."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def readme():
    return (REPO / "README.md").read_text(encoding="utf-8")


def test_readme_section():
    text = readme()
    assert "Apply to jobs you found" in text
    section = text.split("Apply to jobs you found", 1)[1]
    for term in ("hireember add-job", "--apply", "--no-review", "--text", "review", "Add and apply"):
        assert term in section, term


def test_cli_reference_lists_add_job():
    ref = readme().split("## CLI Reference", 1)[1].split("\n## ", 1)[0]
    assert "add-job" in ref


def test_traceability_lists_new_surfaces():
    text = (REPO / "docs" / "traceability.md").read_text(encoding="utf-8")
    for term in ("add-job", "/api/jobs/add", "test_p10_", "AC-14"):
        assert term in text, term


def test_cli_help_and_docstring_mention_adding_jobs_by_url():
    from hireember import cli

    for text in (cli.app.info.help, cli.main.__doc__):
        low = text.lower()
        assert "url" in low and "job" in low and "add" in low
