"""Shared helpers for the phase-7 resume library acceptance tests (public surfaces only)."""

import http.client
import io
import json
import uuid
import zipfile
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from p4_helpers import Client, start_server, stop_server  # noqa: F401  (re-exported)

REPO_ROOT = Path(__file__).resolve().parents[2]
MB10 = 10 * 1024 * 1024

RESUME_TEXT = (
    "Jane Doe\njane@example.com\n\n"
    "Summary\nBackend engineer with Python and SQL experience.\n\n"
    "Experience\nAcme Corp - built Python APIs with FastAPI.\nGlobex - wrote Kubernetes deployment scripts.\n\n"
    "Education\nBSc Computer Science, Your University\n\n"
    "Skills\nPython, SQL, Docker\n"
)


def base_dir() -> Path:
    from hireember import config

    return config.APP_DIR / "base_resumes"


def stored_files() -> set:
    d = base_dir()
    return {p.name for p in d.iterdir()} if d.exists() else set()


def text_file(tmp_path, text=RESUME_TEXT, name=None) -> Path:
    path = tmp_path / (name or f"cv_{uuid.uuid4().hex[:6]}.txt")
    path.write_bytes(text.encode("utf-8"))
    return path


def _para(text):
    return f"<w:p><w:r><w:t xml:space=\"preserve\">{escape(text)}</w:t></w:r></w:p>"


def docx_bytes(items) -> bytes:
    """A minimal .docx. ``items`` is a list of str (paragraph) or list-of-rows (table; row = list of str)."""
    body = []
    for item in items:
        if isinstance(item, str):
            body.append(_para(item))
        else:
            rows = "".join(
                "<w:tr>" + "".join(f"<w:tc>{_para(c)}</w:tc>" for c in row) + "</w:tr>" for row in item)
            body.append(f"<w:tbl><w:tblPr/><w:tblGrid/>{rows}</w:tbl>")
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:document xmlns:w="{ns}"><w:body>{"".join(body)}</w:body></w:document>')
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType='
        '"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
        'officeDocument" Target="word/document.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
    return buf.getvalue()


def blank_pdf_bytes() -> bytes:
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def multipart(fields: dict, filename: str, data: bytes):
    """Build a multipart/form-data body; returns (body, content_type)."""
    boundary = "----p7boundary" + uuid.uuid4().hex
    out = b""
    for key, value in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n").encode()
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n").encode() + data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, f"multipart/form-data; boundary={boundary}"


def _send(client: Client, headers: dict, data: bytes):
    """POST /api/resumes; tolerate a server that answers (e.g. 413) before reading the whole body."""
    conn = http.client.HTTPConnection("127.0.0.1", client.port, timeout=60)
    try:
        conn.putrequest("POST", "/api/resumes")
        for key, value in {**headers, "Content-Length": str(len(data))}.items():
            conn.putheader(key, value)
        conn.endheaders()
        try:
            conn.sock.sendall(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
        resp = conn.getresponse()
        payload = resp.read()
        return resp.status, json.loads(payload.decode("utf-8")) if payload else None
    finally:
        conn.close()


def post_raw(client: Client, filename: str, data: bytes, name: str, tags: str = ""):
    headers = {"X-Filename": quote(filename), "X-Name": quote(name), "Content-Type": "application/octet-stream"}
    if tags:
        headers["X-Tags"] = quote(tags)
    return _send(client, headers, data)


def post_multipart(client: Client, filename: str, data: bytes, name: str, tags: str = ""):
    body, ctype = multipart({"name": name, "tags": tags}, filename, data)
    return _send(client, {"Content-Type": ctype}, body)


def row_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM resumes").fetchone()[0]


def chunk_rows(conn, resume_id):
    return conn.execute("SELECT section, position FROM resume_chunks WHERE resume_id = ? ORDER BY position",
                        (resume_id,)).fetchall()
