"""Model tiers: ``fast`` (scoring, discovery, enrichment) and ``quality`` (tailoring, cover letters).

Settings live in ``models.toml`` in the data folder. When a tier has no section there, the
legacy environment variables (GEMINI_API_KEY, OPENAI_API_KEY, LLM_URL) still apply, through
``hireember.llm._detect_provider``.
"""

from __future__ import annotations

import json
import os
import re
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from hireember import config

TIERS = ("fast", "quality")
PROVIDERS = ("gemini", "openai", "custom")

_PRESETS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.0-flash", "GEMINI_API_KEY"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_BAD_TIER = "Tier must be 'fast' or 'quality'."

# stage name -> (label, tier), in display order
_STAGES = {
    "discover": ("discovery", "fast"),
    "enrich": ("enrichment", "fast"),
    "score": ("scoring", "fast"),
    "tailor": ("tailoring", "quality"),
    "cover": ("cover letters", "quality"),
}


class ModelsError(Exception):
    """Base class; ``str(e)`` is a one-line message fit for the user."""


class ModelsConfigError(ModelsError):
    """models.toml cannot be read."""


class TierNotConfigured(ModelsError):
    """A tier has no usable settings."""


@dataclass(frozen=True)
class TierSettings:
    tier: str
    provider: str
    model: str
    base_url: str
    api_key: str
    source: str  # "config file" or "environment"

    @property
    def is_local(self) -> bool:
        return (urlparse(self.base_url).hostname or "") in _LOCAL_HOSTS

    @property
    def key_state(self) -> str:
        if self.is_local:
            return "not needed (local)"
        return "set" if self.api_key else "not set"


@dataclass(frozen=True)
class TierResult:
    tier: str
    ok: bool
    provider: str
    model: str
    seconds: float
    message: str


# -- the file ----------------------------------------------------------------

def _path(path: Path | None) -> Path:
    return Path(path) if path is not None else Path(config.MODELS_PATH)


def _toml_error(path: Path, line: int) -> ModelsConfigError:
    return ModelsConfigError(f"models.toml is not valid TOML (line {line}). Fix or delete it: {path}")


def load_models_file(path: Path | None = None) -> dict[str, dict[str, str]]:
    """Read models.toml; ``{}`` when absent. Raises ModelsConfigError on bad TOML."""
    p = _path(path)
    if not p.exists():
        return {}
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        m = re.search(r"line (\d+)", str(e))
        raise _toml_error(p, int(m.group(1)) if m else 1) from e
    except (OSError, UnicodeDecodeError) as e:
        raise _toml_error(p, 1) from e
    return {
        name: {k: str(v) for k, v in section.items()}
        for name, section in data.items()
        if isinstance(section, dict)
    }


def _write(path: Path, data: dict[str, dict[str, str]]) -> None:
    lines: list[str] = []
    for name in [*TIERS, *sorted(set(data) - set(TIERS))]:
        section = data.get(name)
        if not section:
            continue
        if lines:
            lines.append("")
        lines.append(f"[{name}]")
        lines.extend(f"{key} = {json.dumps(value)}" for key, value in section.items())
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def save_tier(tier: str, *, provider: str | None = None, model: str | None = None,
              base_url: str | None = None, api_key: str | None = None, path: Path | None = None) -> Path:
    """Merge the given fields into the tier's section of models.toml and return the file path."""
    if tier not in TIERS:
        raise ValueError(_BAD_TIER)
    if provider is not None and provider not in PROVIDERS:
        raise ValueError("Provider must be 'gemini', 'openai' or 'custom'.")
    p = _path(path)
    data = load_models_file(p)
    section = dict(data.get(tier, {}))
    for key, value in (("provider", provider), ("model", model), ("base_url", base_url), ("api_key", api_key)):
        if value is not None:
            section[key] = value
    data[tier] = section
    _write(p, data)
    return p


# -- resolution --------------------------------------------------------------

def _not_configured(tier: str) -> TierNotConfigured:
    return TierNotConfigured(
        f"{tier} tier is not configured. Run 'hireember models set {tier}' or 'hireember init'."
    )


def _provider_of(base_url: str) -> str:
    for name, (url, _model, _env) in _PRESETS.items():
        if base_url == url:
            return name
    return "custom"


def _from_environment(tier: str, model: str | None = None) -> TierSettings:
    from hireember import llm

    try:
        base_url, env_model, api_key = llm._detect_provider()
    except RuntimeError:
        raise _not_configured(tier) from None
    return TierSettings(tier, _provider_of(base_url), model or env_model, base_url, api_key, "environment")


def resolve_tier(tier: str, path: Path | None = None) -> TierSettings:
    """Settings for ``tier``: its models.toml section first, then the legacy environment."""
    if tier not in TIERS:
        raise ValueError(_BAD_TIER)
    section = load_models_file(path).get(tier)
    if not section:
        return _from_environment(tier)

    provider = section.get("provider", "")
    base_url = section.get("base_url", "").rstrip("/")
    if provider and provider not in PROVIDERS:
        raise ModelsConfigError(
            f"models.toml: provider '{provider}' is not valid for the {tier} tier. "
            f"Use gemini, openai or custom: {_path(path)}"
        )
    if not provider:
        if not base_url:
            return _from_environment(tier, section.get("model"))
        provider = "custom"

    if provider == "custom":
        if not base_url:
            raise _not_configured(tier)
        model = section.get("model") or os.environ.get("LLM_MODEL") or "local-model"
        key_env = "LLM_API_KEY"
    else:
        preset_url, default_model, key_env = _PRESETS[provider]
        base_url = base_url or preset_url
        model = section.get("model") or default_model
    api_key = section.get("api_key") or os.environ.get(key_env, "")
    settings = TierSettings(tier, provider, model, base_url, api_key, "config file")
    if provider != "custom" and not api_key and not settings.is_local:
        raise TierNotConfigured(
            f"{tier} tier has no API key. Set it with 'hireember models set {tier} --api-key ...' "
            "or the GEMINI_API_KEY / OPENAI_API_KEY variable."
        )
    return settings


def key_origin(settings: TierSettings, path: Path | None = None) -> str:
    """Where the key comes from: ``set (config file)``, ``set (environment)``, ``not set`` or the local note."""
    if settings.is_local:
        return settings.key_state
    if not settings.api_key:
        return "not set"
    if settings.source == "config file":
        try:
            if load_models_file(path).get(settings.tier, {}).get("api_key"):
                return "set (config file)"
        except ModelsError:
            pass
    return "set (environment)"


# -- testing -----------------------------------------------------------------

def friendly_error(exc: Exception, settings: TierSettings | None = None) -> str:
    """One line describing a failed model call. No traceback text and no exception class names."""
    provider = settings.provider if settings else "the provider"
    if isinstance(exc, ModelsError):
        return str(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return f"Key rejected by {provider}"
        if code == 404:
            return f"Model '{settings.model if settings else 'unknown'}' not found"
        return f"{provider} returned HTTP {code}"
    if isinstance(exc, httpx.TimeoutException):
        return "Request timed out"
    if isinstance(exc, httpx.RequestError):
        return f"Cannot reach {settings.base_url if settings else 'the server'}"
    text = " ".join(str(exc).split())
    if "403" in text and "Gemini" in text:
        return f"Key rejected by {provider}"
    return (text[:120] or "Request failed")


def test_tier(tier: str) -> TierResult:
    """Make one tiny model call for ``tier``. Never raises."""
    settings = None
    start = time.monotonic()
    try:
        settings = resolve_tier(tier)
        from hireember import llm

        llm.get_client(tier).chat(
            [{"role": "user", "content": "Reply with the single word: ok"}], max_tokens=8, temperature=0.0,
        )
    except Exception as e:  # reported, never raised
        return TierResult(tier, False, settings.provider if settings else "", settings.model if settings else "",
                          time.monotonic() - start, friendly_error(e, settings))
    return TierResult(tier, True, settings.provider, settings.model, time.monotonic() - start, "")


# Pytest would otherwise collect this helper as a test.
test_tier.__test__ = False  # type: ignore[attr-defined]


def probe_tier(tier: str) -> TierResult:
    """Check that the tier's endpoint answers, without generating text. Never raises."""
    settings = None
    start = time.monotonic()
    try:
        settings = resolve_tier(tier)
        headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
        resp = httpx.get(f"{settings.base_url}/models", headers=headers, timeout=5)
        if resp.status_code in (401, 403):
            message = f"Key rejected by {settings.provider}"
        elif resp.status_code >= 500:
            message = f"{settings.provider} returned HTTP {resp.status_code}"
        else:
            message = ""
    except Exception as e:  # reported, never raised
        return TierResult(tier, False, settings.provider if settings else "", settings.model if settings else "",
                          time.monotonic() - start, friendly_error(e, settings))
    return TierResult(tier, not message, settings.provider, settings.model, time.monotonic() - start, message)


def stage_model_lines(stages: list[str]) -> list[str]:
    """``<label>: <model> (<tier>)`` for each executed model stage whose tier is configured."""
    lines: list[str] = []
    for stage, (label, tier) in _STAGES.items():
        if stage not in stages:
            continue
        try:
            lines.append(f"{label}: {resolve_tier(tier).model} ({tier})")
        except (ModelsError, ValueError):
            continue
    return lines
