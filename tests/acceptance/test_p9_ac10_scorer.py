"""Phase 9 AC-10: the scorer prompt carries the title_include role family; 'role family' caps the score."""

import pytest

from p9_helpers import use_config

JOB = {"title": "Account Executive", "site": "Acme", "location": "Berlin", "full_description": "Sell things"}


class Stub:
    def __init__(self, reply):
        self.reply = reply
        self.messages = []

    def chat(self, messages, **kwargs):
        self.messages.append(messages)
        return self.reply


@pytest.fixture
def stub(monkeypatch):
    def make(reply="SCORE: 9\nKEYWORDS: a\nREASONING: Outside the role family."):
        s = Stub(reply)
        monkeypatch.setattr("hireember.scoring.scorer.get_client", lambda *a, **k: s)
        return s
    return make


def test_prompt_contains_role_family_and_rule(tmp_path, monkeypatch, stub):
    from hireember.scoring import scorer

    use_config(tmp_path, monkeypatch, searches={"title_include": ["software engineer", "developer"]})
    s = stub()
    scorer.score_job("RESUME", JOB)
    system, user = s.messages[0][0]["content"], s.messages[0][1]["content"]
    assert "Target role family: software engineer, developer" in user
    assert "role family" in system and "1-3" in system


def test_role_family_reasoning_caps_score(tmp_path, monkeypatch, stub):
    from hireember.scoring import scorer

    use_config(tmp_path, monkeypatch, searches={"title_include": ["engineer"]})
    stub("SCORE: 9\nKEYWORDS: a\nREASONING: Outside the Role Family.")
    assert scorer.score_job("R", JOB)["score"] <= 3
    stub("SCORE: 9\nKEYWORDS: a\nREASONING: Strong match.")
    assert scorer.score_job("R", JOB)["score"] == 9
