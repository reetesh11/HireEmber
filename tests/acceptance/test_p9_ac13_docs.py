"""Phase 9 AC-13: README, searches.example.yaml and traceability document the search-config source of truth."""

from pathlib import Path

import yaml

import hireember

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = Path(hireember.__file__).parent / "config" / "searches.example.yaml"


def test_example_only_has_keys_the_code_reads():
    from hireember.search_config import KNOWN_KEYS

    keys = set(yaml.safe_load(EXAMPLE.read_text(encoding="utf-8")))
    assert keys <= KNOWN_KEYS, sorted(keys - KNOWN_KEYS)
    assert {"title_include", "title_exclude"} <= keys


def test_readme_documents_keys_and_profile_tab():
    text = (REPO / "README.md").read_text(encoding="utf-8")
    for term in ("title_include", "title_exclude", "accept_patterns", "reject_patterns",
                 "personal.country", "Profile"):
        assert term in text, term


def test_traceability_mentions_the_new_surfaces():
    text = (REPO / "docs" / "traceability.md").read_text(encoding="utf-8")
    for term in ("title_include", "test_p9_"):
        assert term in text, term
