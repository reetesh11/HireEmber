import yaml

from hireember import config
from hireember.scoring import scorer

JOB = {"title": "Account Executive", "site": "Acme", "location": "Berlin", "full_description": "Sell"}


class Stub:
    def __init__(self, reply):
        self.reply, self.messages = reply, []

    def chat(self, messages, **kwargs):
        self.messages.append(messages)
        return self.reply


def _setup(tmp_path, monkeypatch, include, reply):
    path = tmp_path / "searches.yaml"
    path.write_text(yaml.safe_dump({"title_include": include}))
    monkeypatch.setattr(config, "SEARCH_CONFIG_PATH", path)
    stub = Stub(reply)
    monkeypatch.setattr(scorer, "get_client", lambda *a, **k: stub)
    return stub


def test_family_line_rule_and_cap(tmp_path, monkeypatch):
    stub = _setup(tmp_path, monkeypatch, ["engineer", "developer"], "SCORE: 8\nKEYWORDS: a\nREASONING: Outside the role family.")
    assert scorer.score_job("R", JOB)["score"] == 3
    system, user = stub.messages[0][0]["content"], stub.messages[0][1]["content"]
    assert "Target role family: engineer, developer" in user and "1-3" in system


def test_empty_include_changes_nothing(tmp_path, monkeypatch):
    stub = _setup(tmp_path, monkeypatch, [], "SCORE: 8\nKEYWORDS: a\nREASONING: role family mentioned.")
    assert scorer.score_job("R", JOB)["score"] == 8
    assert stub.messages[0][0]["content"] == scorer.SCORE_PROMPT
    assert "role family" not in stub.messages[0][1]["content"].lower()
