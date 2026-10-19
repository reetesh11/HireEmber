"""Phase 0d: the resume_extract public functions and the pypdf dependency (AC-2, AC-4, AC-6, AC-7)."""

import re
from pathlib import Path

import pytest

from p0d_helpers import (
    BODY, COUNTRY, CITY, EMAIL, FULL_LINES, LINKEDIN, NAME, PHONE, PROVINCE, write_pdf,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_pypdf_is_a_declared_dependency():
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    deps = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.S | re.M).group(1)
    assert re.search(r'"pypdf\s*>=\s*4', deps)


def test_min_text_chars_is_200():
    from hireember.resume_extract import MIN_TEXT_CHARS

    assert MIN_TEXT_CHARS == 200


def test_extract_text_pdf_returns_words(tmp_path):
    from hireember.resume_extract import extract_pdf_text

    pdf = write_pdf(tmp_path / "r.pdf", FULL_LINES)
    text = extract_pdf_text(pdf)
    assert isinstance(text, str)
    for word in ("distributed", "observability", "ingestion", "PostgreSQL", NAME):
        assert word in text


def test_extract_accepts_str_path(tmp_path):
    from hireember.resume_extract import extract_pdf_text

    pdf = write_pdf(tmp_path / "r.pdf", FULL_LINES)
    assert "observability" in extract_pdf_text(str(pdf))


@pytest.mark.parametrize("kind", ["image-only", "blank-page", "zero-bytes", "corrupt", "missing"])
def test_extract_never_raises_and_returns_empty_for_text_less_files(tmp_path, kind):
    from hireember.resume_extract import extract_pdf_text

    path = tmp_path / "x.pdf"
    if kind == "image-only":
        write_pdf(path, None, rect_only=True)
    elif kind == "blank-page":
        write_pdf(path, None)
    elif kind == "zero-bytes":
        path.write_bytes(b"")
    elif kind == "corrupt":
        path.write_bytes(b"this is not a pdf at all \x00\x01\x02")
    assert extract_pdf_text(path) == ""


def test_propose_full_resume():
    from hireember.resume_extract import propose_profile

    got = propose_profile("\n".join(FULL_LINES))
    assert got == {
        "full_name": NAME,
        "email": EMAIL,
        "phone": PHONE,
        "linkedin_url": LINKEDIN,
        "city": CITY,
        "province_state": PROVINCE,
        "country": COUNTRY,
    }


def test_propose_never_returns_postal_code():
    from hireember.resume_extract import propose_profile

    text = "\n".join(FULL_LINES) + "\nPostal code: M5V 2T6\n"
    assert not any("postal" in k or "zip" in k for k in propose_profile(text))


def test_propose_partial_resume_only_returns_found_fields():
    from hireember.resume_extract import propose_profile

    text = f"{NAME}\n{EMAIL}\n" + "\n".join(BODY)
    assert propose_profile(text) == {"full_name": NAME, "email": EMAIL}


def test_propose_two_emails_gives_no_email():
    from hireember.resume_extract import propose_profile

    got = propose_profile(f"{NAME}\na@example.com | b@example.org\n")
    assert "email" not in got
    assert got.get("full_name") == NAME


def test_propose_two_phones_gives_no_phone():
    from hireember.resume_extract import propose_profile

    got = propose_profile(f"{NAME}\n416-555-0142 | 647-555-0199\n")
    assert "phone" not in got


def test_propose_two_part_header_gives_no_location():
    from hireember.resume_extract import propose_profile

    got = propose_profile(f"{NAME}\nToronto, Ontario\n{EMAIL}\n")
    assert not {"city", "province_state", "country"} & set(got)


def test_propose_two_three_part_segments_give_no_location():
    from hireember.resume_extract import propose_profile

    got = propose_profile(f"{NAME}\nToronto, Ontario, Canada | Boston, Massachusetts, USA\n")
    assert not {"city", "province_state", "country"} & set(got)


def test_propose_location_from_pipe_segment():
    from hireember.resume_extract import propose_profile

    got = propose_profile(f"{NAME}\n{EMAIL} | Calgary, Alberta, Canada\n")
    assert (got["city"], got["province_state"], got["country"]) == ("Calgary", "Alberta", "Canada")


@pytest.mark.parametrize("first_line", ["J. Doe 2nd", "jane@example.com", "Curriculum Vitae of Jane Q. Public Doe", "Resume"])
def test_propose_rejects_implausible_name(first_line):
    from hireember.resume_extract import propose_profile

    assert "full_name" not in propose_profile(f"{first_line}\nsome text\n")


@pytest.mark.parametrize("text", ["", "\x00\x01\x02\xff\xfe binary \x00", "   \n\n  "])
def test_propose_malformed_input_returns_empty(text):
    from hireember.resume_extract import propose_profile

    assert propose_profile(text) == {}
