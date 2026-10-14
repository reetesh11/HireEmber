"""AC-7: a local HTML fixture form is served from 127.0.0.1 without external network."""

import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser


class _FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = 0
        self.inputs: list[str] = []
        self.buttons: list[str] = []
        self.external: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "form":
            self.forms += 1
        elif tag == "input":
            self.inputs.append(a.get("type", "text").lower())
        elif tag == "button":
            self.buttons.append(a.get("type", "submit").lower())
        for key in ("src", "href"):
            if re.match(r"^(https?:)?//", a.get(key, "")):
                self.external.append(a[key])


def test_fixture_form_is_served_locally_with_required_fields(fixture_form_server):
    base = fixture_form_server
    assert urllib.parse.urlparse(base).hostname == "127.0.0.1"

    url = urllib.parse.urljoin(base, "forms/basic_form.html")
    with urllib.request.urlopen(url, timeout=5) as resp:
        assert resp.status == 200
        html = resp.read().decode("utf-8")

    parser = _FormParser()
    parser.feed(html)
    assert parser.forms >= 1
    assert "text" in parser.inputs
    assert "file" in parser.inputs
    assert "submit" in parser.buttons or "submit" in parser.inputs
    assert parser.external == [], f"fixture loads external resources: {parser.external}"
