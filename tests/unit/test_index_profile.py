from pathlib import Path

import hireember

PAGE = (Path(hireember.__file__).parent / "web" / "static" / "index.html").read_text(encoding="utf-8")


def test_profile_tab_and_endpoints():
    assert 'id="tab-profile"' in PAGE and 'id="page-profile"' in PAGE
    assert "/api/profile" in PAGE and "/restore" in PAGE


def test_labels_and_ids():
    for text in ("Remote jobs accepted", "Region/State/Province", "Loading profile...", "Could not load profile.",
                 "Hard-no titles", "Rejected locations", "Where I live", "Remove ", "p-remote", "p-country",
                 "All except dropped", 'id="f-status"'):
        assert text in PAGE, text
