from pathlib import Path

INDEX = Path(__file__).resolve().parents[2] / "src" / "hireember" / "web" / "static" / "index.html"


def test_panel_labels_and_roles():
    html = INDEX.read_text(encoding="utf-8")
    for text in ("Add job URLs", "Job URLs (one per line)", "Add and apply", 'role="status"', 'role="alert"',
                 "Paste job description", "Continue", "/api/jobs/add"):
        assert text in html


def test_no_review_off_switch():
    low = INDEX.read_text(encoding="utf-8").lower()
    assert "no-review" not in low and "review:false" not in low
