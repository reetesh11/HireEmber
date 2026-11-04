"""Shared helpers for the phase-10 add-job-by-URL acceptance tests (public surfaces only)."""

import json
from datetime import datetime, timezone

from p4_helpers import Client, make_ticket, start_server, stop_server  # noqa: F401  (re-exported)

DESC_MARK = "ZX-DESCRIPTION-MARKER"
LONG = (f"{DESC_MARK} You will design, build and run reliable services for our customers every day. "
        "We value clear writing, careful testing and steady delivery across the whole team.")


def public_resolver(host, port, *args, **kwargs):
    """A resolver that maps every name to one public address (no DNS in tests)."""
    return [(2, 1, 6, "", ("93.184.216.34", port or 0))]


def resolver_for(mapping):
    def resolve(host, port, *args, **kwargs):
        out = []
        for ip in mapping[host]:
            if ":" in ip:
                out.append((10, 1, 6, "", (ip, port or 0, 0, 0)))
            else:
                out.append((2, 1, 6, "", (ip, port or 0)))
        return out
    return resolve


def page(url, html, status=200):
    from hireember.urlfetch import FetchResult

    return FetchResult(url=url, status=status, html=html, truncated=False)


def static_fetch(html, status=200):
    return lambda url: page(url, html, status)


def failing_fetch(reason):
    from hireember.urlfetch import FetchError

    def fetch(url):
        raise FetchError(reason)
    return fetch


def no_extract(url, text):
    raise AssertionError("the AI extractor must not be called")


def blank_extract(url, text):
    return {"title": "", "company": "", "location": "", "description": "", "application_url": ""}


JSON_LD_HTML = """<html><head><script type="application/ld+json">%s</script></head>
<body><h1>Backend Engineer</h1></body></html>""" % json.dumps({
    "@context": "https://schema.org", "@type": "JobPosting", "title": "Backend Engineer",
    "description": f"<p>{LONG}</p>",
    "hiringOrganization": {"@type": "Organization", "name": "Acme Corp"},
    "jobLocation": {"@type": "Place", "address": {
        "@type": "PostalAddress", "addressLocality": "Berlin", "addressCountry": "DE"}},
})

GREENHOUSE_HTML = f"""<html><head><meta property="og:title" content="Data Engineer">
<meta property="og:site_name" content="Gardenhouse Labs"></head>
<body><div id="app_body"><div class="content"><h1 class="app-title">Data Engineer</h1>
<div class="location">Remote, Europe</div><div id="content"><p>{LONG}</p></div></div></div></body></html>"""

LEVER_HTML = f"""<html><head><meta property="og:title" content="Product Designer"></head>
<body><div class="posting-page"><h2>Product Designer</h2>
<div class="posting-categories"><div class="location">Lisbon</div></div>
<div><p>{LONG}</p></div></div></body></html>"""

ASHBY_HTML = f"""<html><head><meta property="og:title" content="Site Reliability Engineer">
<meta property="og:site_name" content="Ashen Systems"></head>
<body><h1>Site Reliability Engineer</h1><div class="ashby-job-posting-location">Toronto</div>
<div class="ashby-job-posting-description"><p>{LONG}</p></div></body></html>"""

WORKDAY_HTML = f"""<html><head><meta property="og:site_name" content="Acme Workday"></head>
<body><div data-automation-id="jobPostingPage"><h2 data-automation-id="jobPostingHeader">Business Analyst</h2>
<div data-automation-id="locations" class="job-location">Dublin</div>
<div data-automation-id="jobPostingDescription" class="job-description"><p>{LONG}</p></div></div></body></html>"""

UNKNOWN_HTML = ("<html><head><title>Careers</title></head><body><div class='x1'><h1>Chef de Cuisine</h1>"
                "<p>Come and cook for us in a busy kitchen.</p></div></body></html>")
UNKNOWN_EXTRACT = {"title": "Chef de Cuisine", "company": "Petit Bistro", "location": "Paris",
                   "description": LONG, "application_url": ""}

LOGIN_HTML = ('<html><body><form action="/session"><input type="password" name="pw">'
              '<button>Sign in</button></form></body></html>')

PROFILE_TORONTO = {"personal": {"city": "Toronto", "province_state": "Ontario", "country": "Canada"}}


def job_row(conn, url):
    r = conn.execute(
        "SELECT j.*, c.name AS company_name FROM jobs j LEFT JOIN companies c ON c.id = j.company_id "
        "WHERE j.url = ?", (url,)).fetchone()
    return dict(zip(r.keys(), tuple(r))) if r else None


def job_count(conn):
    return conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]


def ticket_of(conn, url):
    from hireember import tickets

    return tickets.get_ticket_by_url(conn, url)


class Pipeline:
    """Stubs for gating, preflight and the apply launcher; records every call in order."""

    def __init__(self, monkeypatch, *, score=8, block_reason=None, preflight_ok=True, outcomes=None):
        from hireember import gating, preflight
        from hireember.apply import launcher

        self.calls = []
        self.launches = []
        self.score = score
        self.block_reason = block_reason
        self.outcomes = outcomes or {}
        self.preflight_ok = preflight_ok

        def score_stub(conn, url, *a, **k):
            from hireember import tickets
            self.calls.append(("score", url))
            tid = tickets.set_job_score(conn, url, self.score, "stub")
            t = tickets.get_ticket(conn, tid)
            return gating.GateResult(tid, t["status"], t["status_reason"] or "", self.score)

        def tailor_stub(conn, ticket_id, *a, **k):
            from hireember import tickets
            self.calls.append(("tailor", ticket_id))
            if self.block_reason:
                tickets.set_status(conn, ticket_id, "blocked for human", reason=self.block_reason)
            t = tickets.get_ticket(conn, ticket_id)
            return gating.GateResult(ticket_id, t["status"], t["status_reason"] or "", t["score"])

        def preflight_stub(command, stages, **k):
            self.calls.append(("preflight", command))
            return preflight.PreflightOutcome(proceed=self.preflight_ok, stages=[])

        def launcher_stub(**kw):
            from hireember.database import get_connection
            self.calls.append(("launch", kw.get("target_url")))
            self.launches.append(kw)
            status, reason = self.outcomes.get(kw.get("target_url"), ("pending", ""))
            c = get_connection()
            now = datetime.now(timezone.utc).isoformat()
            submitted = now if status == "applied" else None
            c.execute("UPDATE tickets SET status = ?, status_reason = ?, submitted_at = COALESCE(?, submitted_at) "
                      "WHERE job_url = ?", (status, reason, submitted, kw.get("target_url")))
            c.commit()
            return 1 if status == "applied" else 0

        monkeypatch.setattr("hireember.gating.score_job_for_ticket", score_stub)
        monkeypatch.setattr("hireember.gating.tailor_ticket", tailor_stub)
        monkeypatch.setattr("hireember.preflight.run_preflight", preflight_stub)
        monkeypatch.setattr(launcher, "main", launcher_stub)

    @property
    def launched_urls(self):
        return [kw["target_url"] for kw in self.launches]


def job_page_for(monkeypatch, html_by_url=None, *, default_html=None, fail=None):
    """Stub addjob's network fetch. ``html_by_url`` maps normalised URL to HTML; ``fail`` maps to reasons."""
    from hireember.urlfetch import FetchError

    html_by_url = html_by_url or {}
    fail = fail or {}

    def fetch(url, *a, **k):
        if url in fail:
            raise FetchError(fail[url])
        html = html_by_url.get(url, default_html)
        if html is None:
            raise FetchError("The page could not be fetched.")
        return page(url, html)

    monkeypatch.setattr("hireember.addjob.fetch_page", fetch)
    monkeypatch.setattr("hireember.addjob.extract_with_ai", lambda url, text: blank_extract(url, text))


def simple_html(n):
    return (f"<html><head><meta property='og:site_name' content='Co{n}'></head><body>"
            f"<h1>Engineer {n}</h1><div class='job-description'><p>{LONG} #{n}</p></div></body></html>")
