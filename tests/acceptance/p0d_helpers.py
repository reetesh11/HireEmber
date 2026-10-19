"""Shared helpers for the phase-0d acceptance tests (public surfaces only)."""

import io
from pathlib import Path

from rich.console import Console

NAME = "Jane Doe"
EMAIL = "jane.doe@example.com"
PHONE = "416-555-0142"
LINKEDIN = "https://www.linkedin.com/in/janedoe"
CITY, PROVINCE, COUNTRY = "Toronto", "Ontario", "Canada"

BODY = [
    "Senior backend engineer with a focus on distributed systems and observability tooling.",
    "Built reliable ingestion pipelines using Python and PostgreSQL for several product teams.",
    "Mentored junior engineers and led migrations of legacy services to container platforms.",
    "Skilled in writing clear documentation, running incident reviews and improving on-call.",
]

FULL_LINES = [NAME, f"{CITY}, {PROVINCE}, {COUNTRY}", f"{EMAIL} | {PHONE} | {LINKEDIN}", *BODY]
FULL_TEXT = "\n".join(FULL_LINES) + "\n"

DISTINCT_WORDS = ["distributed", "observability", "ingestion", "PostgreSQL"]


def make_pdf(lines: list[str] | None, *, rect_only: bool = False) -> bytes:
    """Build a small valid PDF. ``lines`` are drawn as text; ``None`` draws no text at all."""
    if lines:
        parts = ["BT /F1 11 Tf 14 TL 40 760 Td"]
        for line in lines:
            esc = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            parts.append(f"({esc}) Tj T*")
        parts.append("ET")
        stream = "\n".join(parts)
    elif rect_only:
        stream = "0.5 g 50 50 300 300 re f"
    else:
        stream = ""
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def write_pdf(path: Path, lines: list[str] | None, **kw) -> Path:
    path.write_bytes(make_pdf(lines, **kw))
    return path


def console() -> Console:
    return Console(file=io.StringIO(), width=400)


def output(c: Console) -> str:
    return c.file.getvalue()


class Script:
    """A scripted ``ask``: replies per question (consumed in order), records every call."""

    def __init__(self, replies: dict[str, list[str]], hooks: dict | None = None):
        self.replies = {k: list(v) for k, v in replies.items()}
        self.hooks = hooks or {}
        self.log: list[str] = []
        self.kwargs: list[dict] = []

    def __call__(self, question, **kwargs):
        self.log.append(question)
        self.kwargs.append(kwargs)
        if question in self.hooks:
            self.hooks[question]()
        queue = self.replies.get(question)
        if not queue:
            raise AssertionError(f"unexpected or unscripted question: {question!r} (log: {self.log})")
        return queue.pop(0) if len(queue) > 1 else queue[0]


Q_PATH = "Resume file path"
Q_OVERWRITE = "resume.txt already exists. Overwrite it? [y/N]"
Q_TXT = "Resume .txt file path"
Q_CONFIRM = "Does this look right? [Y/n]"


def isolate(monkeypatch, tmp_path):
    """Point the data folder at tmp_path/data; return (conn, data_dir, src_dir)."""
    import hireember.wizard.init as wiz
    from hireember import config
    from hireember.database import init_db

    data = tmp_path / "data"
    src = tmp_path / "src"
    data.mkdir()
    src.mkdir()
    values = {
        "APP_DIR": data,
        "RESUME_PATH": data / "resume.txt",
        "RESUME_PDF_PATH": data / "resume.pdf",
        "PROFILE_PATH": data / "profile.json",
    }
    for name, value in values.items():
        monkeypatch.setattr(config, name, value)
    # Older wizard code imported these names; keep any such copies in step with config.
    for name, value in values.items():
        if hasattr(wiz, name):
            monkeypatch.setattr(wiz, name, value)
    conn = init_db(tmp_path / "hireember.db")
    return conn, data, src
