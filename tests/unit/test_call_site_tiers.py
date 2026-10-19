"""Every call site asks for its tier by name."""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "hireember"
EXPECTED = {
    "scoring/scorer.py": {"fast"},
    "scoring/tailor.py": {"quality"},
    "scoring/cover_letter.py": {"quality"},
    "discovery/smartextract.py": {"fast"},
    "enrichment/detail.py": {"fast"},
}


def test_call_sites_pass_their_tier():
    for rel, tiers in EXPECTED.items():
        text = (SRC / rel).read_text(encoding="utf-8")
        assert "get_client()" not in text
        assert set(re.findall(r'get_client\("(\w+)"\)', text)) == tiers, rel
