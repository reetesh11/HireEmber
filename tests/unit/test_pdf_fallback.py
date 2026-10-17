from hireember.scoring import pdf


def test_write_text_pdf_is_valid_and_paginates(tmp_path):
    text = "\n".join(f"line (with) \\ parens {i}" for i in range(130)) + "\nCafé"
    out = pdf.write_text_pdf(text, tmp_path / "a.pdf")
    data = out.read_bytes()
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert b"/Count 3" in data


def test_convert_falls_back_when_render_fails(tmp_path, monkeypatch):
    def boom(html, path):
        raise RuntimeError("no browser")

    monkeypatch.setattr(pdf, "render_pdf", boom)
    src = tmp_path / "r.txt"
    src.write_text("Jane Doe\nSUMMARY\nHello", encoding="utf-8")
    out = pdf.convert_to_pdf(src)
    assert out.read_bytes().startswith(b"%PDF-")
