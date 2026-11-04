"""Phase 9 AC-10 neighbour: with title_include empty the scorer prompt and score are unchanged."""

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


def test_no_include_means_no_line_and_no_cap(tmp_path, monkeypatch, stub):
    from hireember.scoring import scorer

    use_config(tmp_path, monkeypatch, searches={"title_exclude": ["sales"]})
    s = stub()
    result = scorer.score_job("R", JOB)
    assert result["score"] == 9
    assert "Target role family" not in s.messages[0][1]["content"]
    assert "role family" not in s.messages[0][0]["content"]
    assert s.messages[0][0]["content"] == scorer.SCORE_PROMPT
