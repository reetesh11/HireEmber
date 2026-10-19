from pypdf import PdfWriter

from hireember.resume_extract import extract_pdf_text, propose_profile


def test_blank_page_pdf_gives_empty(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    path = tmp_path / "blank.pdf"
    with path.open("wb") as fh:
        writer.write(fh)
    assert extract_pdf_text(path) == ""


def test_encrypted_pdf_gives_empty(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt("secret")
    path = tmp_path / "enc.pdf"
    with path.open("wb") as fh:
        writer.write(fh)
    assert extract_pdf_text(path) == ""


def test_corrupt_and_missing_give_empty(tmp_path):
    bad = tmp_path / "x.pdf"
    bad.write_bytes(b"garbage")
    assert extract_pdf_text(bad) == ""
    assert extract_pdf_text(tmp_path / "none.pdf") == ""


def test_year_range_is_not_a_phone():
    assert "phone" not in propose_profile("Jane Doe\nEngineer 2019 - 2023\n")


def test_empty_text():
    assert propose_profile("") == {}


def test_single_phone_and_linkedin_as_written():
    got = propose_profile("Jane Doe\n+1 (416) 555-0142 | www.linkedin.com/in/jane\n")
    assert got["phone"] == "+1 (416) 555-0142"
    assert got["linkedin_url"] == "www.linkedin.com/in/jane"
