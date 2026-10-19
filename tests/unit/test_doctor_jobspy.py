import sys

from hireember import doctor


def test_jobspy_hint_names_active_interpreter(monkeypatch):
    monkeypatch.setitem(sys.modules, "jobspy", None)
    c = doctor._check_jobspy()
    assert c.status == "WARN"
    assert sys.executable in c.note
    assert "--no-deps" not in c.note
