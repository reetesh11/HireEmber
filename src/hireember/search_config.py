"""The one reader of ``searches.yaml`` title and location keys (and their legacy aliases)."""

from __future__ import annotations

import yaml

from hireember import config

KNOWN_KEYS = frozenset({
    "queries", "locations", "location", "location_labels", "tiers", "proxy", "sites", "defaults",
    "glassdoor_location_map", "workday_max_tier", "workday_location_filter", "title_include",
    "title_exclude", "exclude_titles", "location_accept", "location_reject_non_remote",
})


def load() -> dict:
    """Parsed searches.yaml; ``{}`` when missing, unreadable or not a mapping."""
    try:
        data = yaml.safe_load(config.SEARCH_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:  # absent or unreadable file means no search targets
        return {}
    return data if isinstance(data, dict) else {}


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [v for v in value if isinstance(v, str)]
    return []


def title_lists(cfg: dict) -> tuple[list[str], list[str]]:
    """Return (title_include, title_exclude); ``exclude_titles`` is the legacy alias."""
    include = _strings(cfg.get("title_include"))
    exclude = _strings(cfg["title_exclude"] if "title_exclude" in cfg else cfg.get("exclude_titles"))
    return include, exclude


def location_lists(cfg: dict) -> tuple[list[str], list[str]]:
    """Return (accept, reject); the ``location`` block wins over the legacy top-level keys."""
    block = cfg.get("location") if isinstance(cfg.get("location"), dict) else {}
    accept = block.get("accept_patterns")
    reject = block.get("reject_patterns")
    if not isinstance(accept, list):
        accept = cfg.get("location_accept")
    if not isinstance(reject, list):
        reject = cfg.get("location_reject_non_remote")
    return _strings(accept), _strings(reject)
