"""Read a job posting from fetched HTML: the detail cascade (JSON-LD, then selectors, then one AI call)."""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from hireember.enrichment.detail import DESCRIPTION_SELECTORS, clean_description, extract_from_json_ld

log = logging.getLogger(__name__)

MIN_DESCRIPTION = 100
AI_TEXT_LIMIT = 12000

TITLE_SELECTORS = ['[data-automation-id="jobPostingHeader"]', "h1"]
LOCATION_SELECTORS = [
    '[data-automation-id="locations"]', ".ashby-job-posting-location", ".posting-categories .location",
    ".location", '[itemprop="jobLocation"]', '[class*="job-location"]', '[class*="location"]',
]
ATS_HOSTS = ("boards.greenhouse.io", "job-boards.greenhouse.io", "jobs.lever.co", "jobs.ashbyhq.com")
LOGIN_PATH = re.compile(r"/(log-?in|sign-?in|sso|auth)(/|$)", re.IGNORECASE)

AI_PROMPT = """You are reading the visible text of a single job posting web page.

PAGE URL: {url}

Return ONLY valid JSON with these keys, using "" for anything you cannot find:
{{"title": "...", "company": "...", "location": "...", "description": "the full job description text", "application_url": ""}}

No explanation, no markdown.

PAGE TEXT:
{text}"""


def _meta(soup: BeautifulSoup, prop: str) -> str:
    tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return (tag.get("content") or "").strip() if tag else ""


def _text(el) -> str:
    return " ".join(el.get_text(" ").split()) if el else ""


def _json_ld(soup: BeautifulSoup) -> list:
    out = []
    for el in soup.select('script[type="application/ld+json"]'):
        try:
            out.append(json.loads(el.string or el.get_text()))
        except ValueError:
            continue
    return out


def _find_posting(data) -> dict | None:
    if isinstance(data, dict):
        if data.get("@type") == "JobPosting":
            return data
        for item in data.get("@graph") or []:
            found = _find_posting(item)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_posting(item)
            if found:
                return found
    return None


def _posting_location(posting: dict) -> str:
    loc = posting.get("jobLocation")
    if isinstance(loc, list) and loc:
        loc = loc[0]
    if not isinstance(loc, dict):
        return ""
    addr = loc.get("address")
    if isinstance(addr, str):
        return addr
    if not isinstance(addr, dict):
        return ""
    country = addr.get("addressCountry")
    if isinstance(country, dict):
        country = country.get("name")
    parts = [addr.get("addressLocality"), addr.get("addressRegion"), country]
    return ", ".join(str(p) for p in parts if p)


def _slug_company(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    segments = [s for s in parts.path.split("/") if s]
    if host in ATS_HOSTS and segments:
        return segments[0]
    if host.endswith(".myworkdayjobs.com"):
        return host.split(".")[0]
    return ""


def _host_company(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _select_description(soup: BeautifulSoup) -> str:
    for sel in DESCRIPTION_SELECTORS:
        try:
            el = soup.select_one(sel)
        except Exception:  # noqa: BLE001 - an unsupported selector is skipped, as in detail.py
            continue
        if el:
            text = clean_description(el.get_text("\n"))
            if len(text) >= MIN_DESCRIPTION:
                return text
    return ""


def _cascade(html: str, url: str) -> dict | None:
    """JSON-LD, then selectors. Returns the job fields or None when no description is found."""
    soup = BeautifulSoup(html, "html.parser")
    posting = None
    description = ""
    application_url = ""
    intel = {"json_ld": _json_ld(soup)}
    ld = extract_from_json_ld(intel)
    if ld:
        for data in intel["json_ld"]:
            posting = _find_posting(data)
            if posting:
                break
        description = ld["full_description"]
        application_url = ld.get("application_url") or ""
    else:
        description = _select_description(soup)
    if not description:
        return None

    title = ""
    company = ""
    location = ""
    if posting:
        title = str(posting.get("title") or "").strip()
        org = posting.get("hiringOrganization")
        company = str((org.get("name") if isinstance(org, dict) else org) or "").strip()
        location = _posting_location(posting)
    if not title:
        for sel in TITLE_SELECTORS:
            title = _text(soup.select_one(sel))
            if title:
                break
    if not title:
        title = _meta(soup, "og:title") or _text(soup.select_one("h2")) or _text(soup.title)
    if not company:
        company = _meta(soup, "og:site_name") or _slug_company(url) or _host_company(url)
    if not location:
        for sel in LOCATION_SELECTORS:
            location = _text(soup.select_one(sel))
            if location and len(location) < 120:
                break
            location = ""
    return {"title": title, "company": company, "location": location, "description": description,
            "application_url": str(application_url or "")}


def visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, noscript, svg, iframe, nav, header, footer"):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text("\n").split("\n")]
    return "\n".join(line for line in lines if line)


def extract_with_ai(url: str, text: str) -> dict:
    """One model call on the visible page text; returns the same keys as ``parse_job_page``."""
    from hireember.discovery.smartextract import extract_json
    from hireember.llm import get_client

    blank = {"title": "", "company": "", "location": "", "description": "", "application_url": ""}
    prompt = AI_PROMPT.format(url=url, text=text[:AI_TEXT_LIMIT])
    try:
        raw = get_client("fast").ask(prompt, temperature=0.0, max_tokens=4096)
        data = extract_json(raw)
    except Exception as e:  # noqa: BLE001 - a failed model call means "no description found"
        log.error("AI extraction failed: %s", type(e).__name__)
        return blank
    if not isinstance(data, dict):
        return blank
    out = {k: str(data.get(k) or "").strip() for k in blank}
    out["description"] = clean_description(out["description"])
    return out


def parse_job_page(html: str, url: str, *, extract=None) -> dict | None:
    """Read the job fields from a page, or return None when no description can be found.

    ``extract(url, text)`` is called only when the cascade finds no description.
    """
    found = _cascade(html, url)
    if found:
        return found
    if extract is None:
        extract = extract_with_ai
    data = extract(url, visible_text(html)) or {}
    description = clean_description(str(data.get("description") or ""))
    if not description:
        return None
    return {
        "title": str(data.get("title") or "").strip(),
        "company": str(data.get("company") or "").strip() or _slug_company(url) or _host_company(url),
        "location": str(data.get("location") or "").strip(),
        "description": description,
        "application_url": str(data.get("application_url") or "").strip(),
    }


def looks_like_login(html: str, url: str) -> bool:
    """True when the page asks for a sign-in and holds no job description."""
    if _cascade(html, url):
        return False
    soup = BeautifulSoup(html, "html.parser")
    if soup.select_one('input[type="password"]'):
        return True
    return bool(LOGIN_PATH.search(urlsplit(url).path))
