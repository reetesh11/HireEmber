"""Shared helpers for the phase-9 search precision acceptance tests (public surfaces only)."""

import json

import yaml

from p4_helpers import Client, make_ticket, start_server, stop_server  # noqa: F401  (re-exported)
from p5_helpers import Recorder, utc  # noqa: F401  (re-exported)


def use_config(tmp_path, monkeypatch, searches=None, profile=None, raw_searches=None, raw_profile=None):
    """Point config.SEARCH_CONFIG_PATH / PROFILE_PATH at temp files (optionally written); return both paths."""
    from hireember import config

    sp, pp = tmp_path / "searches.yaml", tmp_path / "profile.json"
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", sp)
    monkeypatch.setattr(config, "PROFILE_PATH", pp)
    for mod_name in ("hireember.wizard.init", "hireember.doctor"):
        import importlib

        mod = importlib.import_module(mod_name)
        for attr, val in (("SEARCH_CONFIG_PATH", sp), ("PROFILE_PATH", pp)):
            if hasattr(mod, attr):
                monkeypatch.setattr(mod, attr, val)
    if raw_searches is not None:
        sp.write_text(raw_searches, encoding="utf-8")
    elif searches is not None:
        sp.write_text(yaml.safe_dump(searches, sort_keys=False), encoding="utf-8")
    if raw_profile is not None:
        pp.write_text(raw_profile, encoding="utf-8")
    elif profile is not None:
        pp.write_text(json.dumps(profile), encoding="utf-8")
    return sp, pp


def job_rows(conn):
    return {r["url"]: r for r in conn.execute(
        "SELECT j.url, j.title, t.status AS status, t.status_reason AS reason FROM jobs j "
        "LEFT JOIN tickets t ON t.job_url = j.url")}


FILTER_CFG = {
    "title_exclude": ["sales", "program manager"],
    "title_include": ["engineer"],
    "location": {"accept_patterns": ["Berlin", "Remote"]},
}
