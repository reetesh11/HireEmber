import json
from pathlib import Path

import pytest

import hireember.config as config
from hireember.apply import prompt as prompt_mod
from hireember.apply.prompt import build_prompt

ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN = ("capsolver", "gmail", "send_email", "search_emails", "read_email", "verification code",
             "sign up", "signup", "create an account", "create account")


@pytest.fixture
def prompt_text(tmp_path, monkeypatch):
    profile = json.loads((ROOT / "profile.example.json").read_text(encoding="utf-8"))
    profile["personal"]["password"] = "s3cret-pw-value"
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    monkeypatch.setattr(config, "PROFILE_PATH", path)
    monkeypatch.setattr(config, "APPLY_WORKER_DIR", tmp_path / "workers")
    resume = tmp_path / "r.txt"
    resume.write_text("x")
    resume.with_suffix(".pdf").write_bytes(b"%PDF-1.4")
    job = {"url": "https://j/1", "title": "Eng", "site": "Acme", "tailored_resume_path": str(resume)}
    return build_prompt(job, "resume text")


def test_prompt_is_gate_driven_and_clean(prompt_text):
    low = prompt_text.lower()
    assert not [w for w in FORBIDDEN if w in low]
    assert "s3cret-pw-value" not in prompt_text
    for word in ("answer_field", "stop", "before_submit", "submit_pressed", "submitted", "closed"):
        assert word in low


def test_captcha_section_is_gone():
    assert not hasattr(prompt_mod, "_build_captcha_section")
