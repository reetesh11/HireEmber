import hashlib

from hireember import config
from hireember.database import init_db
from hireember.resumes import list_resumes
from hireember.wizard.init import run_resume_step

BODY = "Backend engineer building distributed systems and data pipelines. " * 5


def _env(monkeypatch, tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(config, "APP_DIR", data)
    monkeypatch.setattr(config, "RESUME_PATH", data / "resume.txt")
    monkeypatch.setattr(config, "RESUME_PDF_PATH", data / "resume.pdf")
    return init_db(tmp_path / "t.db"), data


def _ask(replies):
    log = []

    def ask(question, **kwargs):
        log.append(question)
        return replies[question].pop(0) if len(replies[question]) > 1 else replies[question][0]

    ask.log = log
    return ask


def test_edited_extracted_text_is_user_supplied(monkeypatch, tmp_path):
    conn, data = _env(monkeypatch, tmp_path)
    (data / "resume.txt").write_text("edited", encoding="utf-8")
    (data / ".resume_txt_sha256").write_text(hashlib.sha256(b"original").hexdigest())
    src = tmp_path / "me.txt"
    src.write_text(BODY, encoding="utf-8")
    ask = _ask({"Resume file path": [str(src)], "resume.txt already exists. Overwrite it? [y/N]": ["n"],
                "Does this look right? [Y/n]": ["y"]})
    run_resume_step(conn, ask)
    assert (data / "resume.txt").read_text(encoding="utf-8") == "edited"
    assert len(ask.log) == 3


def test_txt_copy_removes_marker_and_registers_once(monkeypatch, tmp_path):
    conn, data = _env(monkeypatch, tmp_path)
    (data / ".resume_txt_sha256").write_text("stale")
    src = tmp_path / "me.txt"
    src.write_text(BODY, encoding="utf-8")
    ask = _ask({"Resume file path": [str(src)], "resume.txt already exists. Overwrite it? [y/N]": ["y"],
                "Does this look right? [Y/n]": ["y"]})
    run_resume_step(conn, ask)
    run_resume_step(conn, ask)
    assert not (data / ".resume_txt_sha256").exists()
    assert len(list_resumes(conn)) == 1
