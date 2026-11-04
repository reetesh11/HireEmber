"""The one reader of ``searches.yaml`` title and location keys (and their legacy aliases)."""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path

import yaml

from hireember import config

KNOWN_KEYS = frozenset({
    "queries", "locations", "location", "location_labels", "tiers", "proxy", "sites", "defaults",
    "glassdoor_location_map", "workday_max_tier", "workday_location_filter", "title_include",
    "title_exclude", "exclude_titles", "location_accept", "location_reject_non_remote", "boards",
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


# -- Profile settings: read and write the keys the dashboard Profile tab edits ----------------

_PERSONAL_KEYS = ("city", "province_state", "country")
_LIST_FIELDS = ("title_include", "title_exclude", "location_accept", "location_reject")
_MAX_LEN = 80


class SettingsError(ValueError):
    """A settings value failed validation; ``field`` names the payload key."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


class UnreadableConfigError(Exception):
    """searches.yaml or profile.json exists but cannot be parsed."""


def _read_yaml_strict() -> tuple[dict, bytes | None]:
    path = Path(config.SEARCH_CONFIG_PATH)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}, None
    except OSError as e:
        raise UnreadableConfigError(f"Could not read searches.yaml: {e}") from e
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as e:
        raise UnreadableConfigError(f"Could not read searches.yaml: {' '.join(str(e).split())}") from e
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise UnreadableConfigError("Could not read searches.yaml: expected a mapping at the top level")
    return data, raw


def _read_json_strict() -> tuple[dict, bytes | None]:
    path = Path(config.PROFILE_PATH)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {}, None
    except OSError as e:
        raise UnreadableConfigError(f"Could not read profile.json: {e}") from e
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise UnreadableConfigError(f"Could not read profile.json: {' '.join(str(e).split())}") from e
    if not isinstance(data, dict):
        raise UnreadableConfigError("Could not read profile.json: expected an object at the top level")
    return data, raw


def _has_remote(cfg: dict) -> bool:
    entries = cfg.get("locations")
    return any(isinstance(e, dict) and bool(e.get("remote")) for e in entries) if isinstance(entries, list) else False


def _personal(profile: dict) -> dict:
    personal = profile.get("personal") if isinstance(profile.get("personal"), dict) else {}
    return {k: personal[k] if isinstance(personal.get(k), str) else "" for k in _PERSONAL_KEYS}


def _settings(cfg: dict, profile: dict) -> dict:
    include, exclude = title_lists(cfg)
    accept, reject = location_lists(cfg)
    return {"title_include": include, "title_exclude": exclude, "location_accept": accept,
            "location_reject": reject, "remote": _has_remote(cfg), "personal": _personal(profile)}


def read_settings() -> dict:
    """The editable settings, with legacy keys normalised; raises UnreadableConfigError on bad files."""
    cfg, _ = _read_yaml_strict()
    profile, _ = _read_json_strict()
    return _settings(cfg, profile)


def _clean_list(field: str, value) -> list[str]:
    if not isinstance(value, list):
        raise SettingsError("Enter a list of keywords.", field)
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise SettingsError("Enter text.", field)
        term = item.strip()
        if not term:
            raise SettingsError("Enter a keyword.", field)
        if len(term) > _MAX_LEN:
            raise SettingsError("Keep entries under 80 characters.", field)
        if term.casefold() in seen:
            raise SettingsError(f"'{term}' is already in the list.", field)
        seen.add(term.casefold())
        out.append(term)
    return out


def _validate(payload: dict) -> dict:
    clean: dict = {}
    for field in _LIST_FIELDS:
        if field in payload:
            clean[field] = _clean_list(field, payload[field])
    if "remote" in payload:
        if not isinstance(payload["remote"], bool):
            raise SettingsError("remote must be true or false.", "remote")
        clean["remote"] = payload["remote"]
    if "personal" in payload:
        personal = payload["personal"]
        if not isinstance(personal, dict):
            raise SettingsError("Enter text.", "personal")
        clean_personal: dict = {}
        for key in _PERSONAL_KEYS:
            if key not in personal:
                continue
            value = personal[key]
            if not isinstance(value, str):
                raise SettingsError("Enter text.", f"personal.{key}")
            value = value.strip()
            if len(value) > _MAX_LEN:
                raise SettingsError("Keep entries under 80 characters.", f"personal.{key}")
            clean_personal[key] = value
        clean["personal"] = clean_personal
    return clean


def _apply(cfg: dict, profile: dict, clean: dict) -> tuple[dict, dict]:
    cfg, profile = copy.deepcopy(cfg), copy.deepcopy(profile)
    if "title_include" in clean:
        cfg["title_include"] = clean["title_include"]
    if "title_exclude" in clean:
        cfg["title_exclude"] = clean["title_exclude"]
        cfg.pop("exclude_titles", None)
    for field, key, legacy in (("location_accept", "accept_patterns", "location_accept"),
                               ("location_reject", "reject_patterns", "location_reject_non_remote")):
        if field in clean:
            block = cfg.get("location") if isinstance(cfg.get("location"), dict) else {}
            block[key] = clean[field]
            cfg["location"] = block
            cfg.pop(legacy, None)
    if "remote" in clean:
        entries = cfg.get("locations") if isinstance(cfg.get("locations"), list) else []
        if clean["remote"]:
            if not _has_remote({"locations": entries}):
                entries.append({"location": "Remote", "remote": True})
        else:
            for entry in entries:
                if isinstance(entry, dict):
                    entry["remote"] = False
        cfg["locations"] = entries
    if clean.get("personal"):
        personal = profile.get("personal") if isinstance(profile.get("personal"), dict) else {}
        personal.update(clean["personal"])
        profile["personal"] = personal
    return cfg, profile


def _temp_for(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return name


def _restore(path: Path, original: bytes | None) -> None:
    if original is None:
        path.unlink(missing_ok=True)
        return
    tmp = _temp_for(path, original)
    try:
        os.replace(tmp, path)
    except OSError:
        path.write_bytes(original)
    finally:
        Path(tmp).unlink(missing_ok=True)


def save_settings(payload: dict) -> dict:
    """Validate and write the settings to searches.yaml and profile.json; return the re-read settings."""
    if not isinstance(payload, dict):
        raise SettingsError("Send a JSON object.", None)
    cfg, cfg_raw = _read_yaml_strict()
    profile, prof_raw = _read_json_strict()
    clean = _validate(payload)
    new_cfg, new_profile = _apply(cfg, profile, clean)
    ypath, ppath = Path(config.SEARCH_CONFIG_PATH), Path(config.PROFILE_PATH)
    writes: list[tuple[Path, bytes, bytes | None]] = []
    if new_cfg != cfg or (cfg_raw is None and _touches_search(clean)):
        data = yaml.safe_dump(new_cfg, sort_keys=False, allow_unicode=True).encode("utf-8")
        writes.append((ypath, data, cfg_raw))
    if new_profile != profile or (prof_raw is None and clean.get("personal")):
        data = (json.dumps(new_profile, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        writes.append((ppath, data, prof_raw))
    temps: list[str] = []
    done: list[tuple[Path, bytes | None]] = []
    try:
        for path, data, _ in writes:
            temps.append(_temp_for(path, data))
        for (path, _, original), tmp in zip(writes, temps):
            os.replace(tmp, path)
            done.append((path, original))
    except BaseException:
        for path, original in reversed(done):
            _restore(path, original)
        raise
    finally:
        for tmp in temps:
            Path(tmp).unlink(missing_ok=True)
    return read_settings()


def _touches_search(clean: dict) -> bool:
    return any(k != "personal" for k in clean)
