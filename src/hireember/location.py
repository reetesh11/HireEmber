"""Deterministic location check used before a job is scored.

``location_skip_reason`` says whether a job's location text clearly does not fit the
candidate's targets. It is conservative: no targets, blank, placeholder or unrecognisable
text (no known region or country) never skips a job. A country target (Canada, US) accepts any
of its provinces, territories or states; a region target accepts that region only. Bare ``CA``
is California, and Canada too when no country is named. No LLM is involved.
"""

from __future__ import annotations

import re
import unicodedata

import yaml

from hireember import config

_PLACEHOLDERS = {"na", "nan", "none", "tbd", "various", "multiple locations", "unknown", "worldwide", "global"}
_REMOTE_WORDS = {"remote", "wfh", "telecommute", "virtual"}
_REMOTE_PHRASES = (("work", "from", "home"),)
_OTHER_WORDS = {"hybrid"}  # stripped before matching the rest, but never passes on its own
_REMOTE_ACCEPT = {"remote", "anywhere"}

# alias phrase -> canonical token; abbreviations and full names map to the same token.
_REGIONS = {
    "on": ["ontario"], "bc": ["british columbia"], "ab": ["alberta"], "qc": ["quebec"], "mb": ["manitoba"],
    "sk": ["saskatchewan"], "ns": ["nova scotia"], "nb": ["new brunswick"],
    "nl": ["newfoundland and labrador", "newfoundland"], "pe": ["prince edward island"],
    "nt": ["northwest territories"], "nu": ["nunavut"], "yt": ["yukon"],
    "al": ["alabama"], "ak": ["alaska"], "az": ["arizona"], "ar": ["arkansas"], "ca": ["california"],
    "co": ["colorado"], "ct": ["connecticut"], "de": ["delaware"], "dc": ["district of columbia"],
    "fl": ["florida"], "ga": ["georgia"], "hi": ["hawaii"], "id": ["idaho"], "il": ["illinois"],
    "in": ["indiana"], "ia": ["iowa"], "ks": ["kansas"], "ky": ["kentucky"], "la": ["louisiana"],
    "me": ["maine"], "md": ["maryland"], "ma": ["massachusetts"], "mi": ["michigan"], "mn": ["minnesota"],
    "ms": ["mississippi"], "mo": ["missouri"], "mt": ["montana"], "ne": ["nebraska"], "nv": ["nevada"],
    "nh": ["new hampshire"], "nj": ["new jersey"], "nm": ["new mexico"], "ny": ["new york"],
    "nc": ["north carolina"], "nd": ["north dakota"], "oh": ["ohio"], "ok": ["oklahoma"], "or": ["oregon"],
    "pa": ["pennsylvania"], "ri": ["rhode island"], "sc": ["south carolina"], "sd": ["south dakota"],
    "tn": ["tennessee"], "tx": ["texas"], "ut": ["utah"], "vt": ["vermont"], "va": ["virginia"],
    "wa": ["washington"], "wv": ["west virginia"], "wi": ["wisconsin"], "wy": ["wyoming"],
    "us": ["usa", "united states", "united states of america"],
    "uk": ["united kingdom", "great britain", "gb"],
    "canada": [],
}
_COUNTRIES = {"us", "uk", "canada"}
_CANADA_REGIONS = {"on", "bc", "ab", "qc", "mb", "sk", "ns", "nb", "nl", "pe", "nt", "nu", "yt"}
# region token -> country token (Canadian provinces and territories; US states and DC)
_REGION_COUNTRY = {r: ("canada" if r in _CANADA_REGIONS else "us") for r in _REGIONS if r not in _COUNTRIES}
_ALIASES: dict[tuple[str, ...], str] = {}
for _canon, _names in _REGIONS.items():
    _ALIASES[(_canon,)] = _canon
    for _name in _names:
        _ALIASES[tuple(_name.split())] = _canon
_MAX_ALIAS_WORDS = max(len(k) for k in _ALIASES)


def _words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.findall(r"[a-z0-9]+", text.lower().replace(".", "").replace("'", ""))


def _canonical(words: list[str]) -> list[str]:
    """Replace region and country names and abbreviations by one canonical token."""
    out: list[str] = []
    i = 0
    while i < len(words):
        for n in range(min(_MAX_ALIAS_WORDS, len(words) - i), 0, -1):
            canon = _ALIASES.get(tuple(words[i:i + n]))
            if canon is not None:
                out.append(canon)
                i += n
                break
        else:
            out.append(words[i])
            i += 1
    return out


def _phrase(text: str) -> list[str]:
    return _canonical(_words(text))


def _contains(words: list[str], phrase: list[str]) -> bool:
    n = len(phrase)
    return n > 0 and any(words[i:i + n] == phrase for i in range(len(words) - n + 1))


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [v for v in value if isinstance(v, str)]
    return []


def _load_search_cfg() -> dict:
    try:
        data = yaml.safe_load(config.SEARCH_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:  # absent or unreadable file means no search targets
        return {}
    return data if isinstance(data, dict) else {}


def _targets(profile: dict | None, cfg: dict) -> tuple[list[list[str]], list[list[str]], bool]:
    """Return (accept phrases, reject phrases, remote accepted)."""
    loc_cfg = cfg.get("location") if isinstance(cfg.get("location"), dict) else {}
    accept = _strings(loc_cfg.get("accept_patterns")) + _strings(cfg.get("location_accept"))
    reject = _strings(loc_cfg.get("reject_patterns")) + _strings(cfg.get("location_reject_non_remote"))
    remote = False
    entries = cfg.get("locations")
    for entry in entries if isinstance(entries, list) else []:
        if isinstance(entry, dict):
            accept += _strings(entry.get("location"))
            remote = remote or bool(entry.get("remote"))
    personal = (profile or {}).get("personal")
    for key in ("city", "province_state", "country"):
        accept += _strings(personal.get(key)) if isinstance(personal, dict) else []
    accept_phrases = [p for p in (_phrase(a) for a in accept) if p]
    reject_phrases = [p for p in (_phrase(r) for r in reject) if p]
    remote = remote or any(p[0] in _REMOTE_ACCEPT and len(p) == 1 for p in accept_phrases)
    return accept_phrases, reject_phrases, remote


def _strip_remote_words(words: list[str]) -> tuple[list[str], bool]:
    """Remove remote wording; return (remainder, whether remote wording was present)."""
    found = False
    out: list[str] = []
    i = 0
    while i < len(words):
        if tuple(words[i:i + 3]) in _REMOTE_PHRASES:
            found = True
            i += 3
        elif words[i] in _REMOTE_WORDS:
            found = True
            i += 1
        elif words[i] in _OTHER_WORDS:
            i += 1
        else:
            out.append(words[i])
            i += 1
    return out, found


def _part_passes(part: str, accept: list[list[str]], reject: list[list[str]], remote_ok: bool) -> bool:
    words = _canonical(_words(part))
    if not words or not any(c.isalpha() for c in part):
        return True
    if " ".join(words) in _PLACEHOLDERS or "".join(words) in _PLACEHOLDERS:
        return True
    rest, remote_wording = _strip_remote_words(words)
    if remote_wording and remote_ok:
        return True
    rest = [w for w in rest if w not in ("and", "or", "the", "of")] if remote_wording else rest
    if not rest:
        return True
    if any(_contains(rest, r) for r in reject):
        return False
    if not accept:
        return True
    tokens = set(rest)
    regions = tokens & _REGION_COUNTRY.keys()
    countries = tokens & _COUNTRIES
    if not regions and not countries:
        return True  # no recognised region or country: nothing to judge by
    implied = countries | {_REGION_COUNTRY[r] for r in regions}
    if "ca" in tokens and not countries:
        implied.add("canada")  # bare CA is California or Canada
    for a in accept:
        if _contains(rest, a):
            return True
        if len(a) == 1:
            if a[0] in _COUNTRIES and a[0] in implied:
                return True  # a country target accepts any region of that country
            if a[0] in _REGION_COUNTRY and not regions and _REGION_COUNTRY[a[0]] in countries:
                return True  # a region target accepts text naming only its country
    return False


def location_skip_reason(location: str | None, profile: dict | None = None,
                         search_cfg: dict | None = None) -> str | None:
    """Return ``location: <text>`` when the job's location fits none of the targets, else None."""
    if not location or not isinstance(location, str):
        return None
    cfg = _load_search_cfg() if search_cfg is None else search_cfg
    accept, reject, remote_ok = _targets(profile, cfg if isinstance(cfg, dict) else {})
    if not accept and not reject:
        return None
    parts = [p for p in re.split(r"[;|]", location) if p.strip()]
    if not parts or any(_part_passes(p, accept, reject, remote_ok) for p in parts):
        return None
    return f"location: {location}"
