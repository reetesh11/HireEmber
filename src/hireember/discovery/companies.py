"""Discovery over the user's company list: one adapter per ATS type."""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlparse

from hireember import companies, runs
from hireember.database import store_jobs

log = logging.getLogger(__name__)

EMPTY_MESSAGE = "No companies to search. Add one with `hireember company add`."
_LOCALE = re.compile(r"^[a-z]{2}(-[A-Za-z]{2})?$")

Adapter = Callable[[dict], list[dict]]


def workday_employer(careers_url: str, name: str) -> dict:
    """Derive the Workday employer record from https://<tenant>.wd<N>.myworkdayjobs.com/<site_id>."""
    parsed = urlparse(careers_url)
    host = parsed.netloc
    if not host or ".myworkdayjobs.com" not in host:
        raise ValueError(f"Not a Workday careers URL: {careers_url}")
    segments = [s for s in parsed.path.split("/") if s]
    if segments and _LOCALE.match(segments[0]):
        segments = segments[1:]
    if not segments:
        raise ValueError(f"No Workday site id in {careers_url}")
    return {"name": name, "tenant": host.split(".")[0], "site_id": segments[0],
            "base_url": f"{parsed.scheme or 'https'}://{host}"}


def workday_adapter(company: dict) -> list[dict]:
    """Search a Workday employer for each configured query and return role dicts."""
    from hireember import config
    from hireember.discovery import workday

    employer = workday_employer(company["careers_url"], company["name"])
    search_cfg = config.load_search_config()
    queries = [q["query"] for q in search_cfg.get("queries", []) if q.get("query")] or [""]
    accept, reject = workday._load_location_filter(search_cfg)
    seen: dict[str, dict] = {}
    for query in queries:
        found = workday.search_employer(
            company["name"], employer, query, location_filter=bool(accept or reject),
            accept_locs=accept, reject_locs=reject)
        for job in workday.fetch_details(employer, found):
            url = job.get("apply_url") or f"{employer['base_url']}/{employer['site_id']}{job.get('external_path', '')}"
            if url and url not in seen:
                seen[url] = {"title": job.get("title"), "url": url, "location": job.get("location"),
                             "description": job.get("full_description") or None}
    return list(seen.values())


def careers_page_adapter(company: dict) -> list[dict]:
    """Run smart extraction on a careers page; raise when the extraction itself failed."""
    from hireember.discovery import smartextract

    result = smartextract._run_one_site(company["name"], company["careers_url"])
    if result.get("status") in ("LLM_ERROR", "PARSE_ERROR", "EXEC_ERROR"):
        raise RuntimeError(result.get("error") or result["status"])
    if result.get("status") not in ("PASS", "PARTIAL", "FAIL"):
        raise RuntimeError(f"Unexpected result: {result.get('status')}")
    return result.get("jobs") or []


DEFAULT_ADAPTERS: dict[str, Adapter] = {"workday": workday_adapter, "careers-page": careers_page_adapter}


def discover_companies(conn: sqlite3.Connection, *, adapters: dict[str, Adapter] | None = None,
                       run_id: int | None = None, now: datetime | None = None) -> dict:
    """Search exactly the active companies on the list and store what they list."""
    adapters = adapters or DEFAULT_ADAPTERS
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    todo = companies.search_list(conn)
    out = {"found": 0, "new": 0, "existing": 0, "companies": len(todo), "failures": [],
           "message": ""}
    if not todo:
        out["message"] = EMPTY_MESSAGE
        return out
    for company in todo:
        try:
            roles = adapters[company["ats_type"]](company)
            for role in roles:
                role["company"] = company["name"]
            new, existing = store_jobs(conn, roles, site=company["name"],
                                       strategy=company["ats_type"], now=stamp)
        except Exception as e:  # noqa: BLE001 - one bad source must not stop the others
            error = str(e) or type(e).__name__
            log.warning("%s: %s", company["name"], error)
            runs.log_event(conn, run_id, company["name"], error)
            out["failures"].append({"source": company["name"], "error": error})
            continue
        out["new"] += new
        out["existing"] += existing
        out["found"] += new + existing
    ok = out["companies"] - len(out["failures"])
    out["message"] = (f"Searched {ok} of {out['companies']} companies: {out['found']} roles, "
                      f"{out['new']} new.")
    return out
