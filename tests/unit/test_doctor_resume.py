from hireember import config, doctor


def test_resume_txt_next_to_pdf_is_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RESUME_PATH", tmp_path / "resume.txt")
    monkeypatch.setattr(config, "RESUME_PDF_PATH", tmp_path / "resume.pdf")
    (tmp_path / "resume.txt").write_text("text", encoding="utf-8")
    (tmp_path / "resume.pdf").write_bytes(b"%PDF")
    check = doctor._check_resume()
    assert check.status == "OK"
    assert "Only PDF found" not in check.note
