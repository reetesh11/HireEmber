"""Phase 6 AC-2: model and token usage per ticket stage, recorded and shown on the ticket page and API."""

import threading

import pytest

from p6_helpers import (Client, make_llm, make_ticket, openai_body, start_server, stop_server,
                        usage_row)


@pytest.fixture
def conn(isolated_db):
    from hireember.database import init_db

    return init_db()


# -- usage module -----------------------------------------------------------------

def test_stages_and_table_exist(conn):
    from hireember import usage
    from hireember.migration import ensure_phase6_schema

    assert usage.STAGES == ("scoring", "tailoring", "applying")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(stage_usage)")]
    assert cols == ["ticket_id", "stage", "model", "input_tokens", "output_tokens", "total_tokens",
                    "updated_at"]
    ensure_phase6_schema(conn)  # idempotent
    ensure_phase6_schema(conn)


def test_record_sums_tokens_and_keeps_the_latest_model(conn):
    from hireember import usage

    tid = make_ticket(conn, "u1")
    usage.record(conn, tid, "scoring", "model-a", 1000, 100)
    usage.record(conn, tid, "scoring", "model-b", 200, 50)
    got = usage.get_usage(conn, tid)
    assert got["scoring"] == {"model": "model-b", "input_tokens": 1200, "output_tokens": 150,
                              "total_tokens": 1350}
    assert got["tailoring"] is None and got["applying"] is None


def test_record_defaults_empty_model_and_coerces_bad_tokens(conn):
    from hireember import usage

    tid = make_ticket(conn, "u2")
    usage.record(conn, tid, "tailoring", "")
    assert usage.get_usage(conn, tid)["tailoring"] == {"model": "unknown", "input_tokens": 0,
                                                        "output_tokens": 0, "total_tokens": 0}
    usage.record(conn, tid, "applying", "m", -5, "abc")
    assert usage.get_usage(conn, tid)["applying"] == {"model": "m", "input_tokens": 0,
                                                       "output_tokens": 0, "total_tokens": 0}


def test_record_rejects_an_unknown_stage(conn):
    from hireember import usage

    tid = make_ticket(conn, "u3")
    with pytest.raises(ValueError):
        usage.record(conn, tid, "discovering", "m", 1, 1)


def test_get_usage_is_per_ticket_and_empty_without_records(conn):
    from hireember import usage

    a, b = make_ticket(conn, "ua"), make_ticket(conn, "ub")
    usage.record(conn, a, "scoring", "m", 1, 2)
    assert usage.get_usage(conn, b) == {"scoring": None, "tailoring": None, "applying": None}


def test_collector_sums_calls_inside_the_block_only(conn):
    from hireember import usage

    usage.note_call("ignored", 5, 5)  # no collector: a no-op
    with usage.collect() as got:
        assert (got.model, got.input_tokens, got.output_tokens, got.calls) == ("", 0, 0, 0)
        usage.note_call("m1", 10, 2)
        usage.note_call("m2", 5, 1)
    assert (got.model, got.input_tokens, got.output_tokens, got.calls) == ("m2", 15, 3, 2)
    usage.note_call("after", 1, 1)
    assert got.calls == 2


def test_collectors_in_different_threads_do_not_mix():
    from hireember import usage

    results = {}
    barrier = threading.Barrier(2)

    def work(name, tokens):
        with usage.collect() as got:
            barrier.wait(5)
            for _ in range(3):
                usage.note_call(name, tokens, 1)
            barrier.wait(5)
        results[name] = (got.model, got.input_tokens, got.output_tokens, got.calls)

    threads = [threading.Thread(target=work, args=("a", 10)), threading.Thread(target=work, args=("b", 100))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert results == {"a": ("a", 30, 3, 3), "b": ("b", 300, 3, 3)}


def test_record_collected_records_only_when_a_call_was_made(conn):
    from hireember import usage

    tid = make_ticket(conn, "rc")
    with usage.collect() as empty:
        pass
    usage.record_collected(conn, tid, "scoring", empty)
    assert usage.get_usage(conn, tid)["scoring"] is None
    with usage.collect() as got:
        usage.note_call("m", 7, 3)
    usage.record_collected(conn, tid, "scoring", got)
    assert usage.get_usage(conn, tid)["scoring"] == {"model": "m", "input_tokens": 7,
                                                      "output_tokens": 3, "total_tokens": 10}


# -- LLM client reads provider usage ----------------------------------------------

def test_llm_client_reports_openai_style_usage_and_still_returns_text():
    from hireember import usage

    client, _ = make_llm("gpt-test", lambda url, payload: (200, openai_body("hello", 11, 7)))
    with usage.collect() as got:
        assert client.chat([{"role": "user", "content": "hi"}]) == "hello"
    assert (got.model, got.input_tokens, got.output_tokens, got.calls) == ("gpt-test", 11, 7, 1)


def test_llm_client_counts_missing_usage_as_zero():
    from hireember import usage

    client, _ = make_llm("m", lambda url, payload: (200, openai_body("hello")))
    with usage.collect() as got:
        assert client.chat([{"role": "user", "content": "hi"}]) == "hello"
    assert (got.input_tokens, got.output_tokens, got.calls) == (0, 0, 1)


def test_llm_client_reads_gemini_native_usage():
    from hireember import usage
    from hireember.llm import LLMClient

    def respond(url, payload):
        if url.endswith("/chat/completions"):
            return 403, {"error": "forbidden"}
        return 200, {"candidates": [{"content": {"parts": [{"text": "native hello"}]}}],
                     "usageMetadata": {"promptTokenCount": 21, "candidatesTokenCount": 9}}

    client = LLMClient("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-test", "k")
    from p6_helpers import FakeHttp

    client._client = FakeHttp(respond)
    with usage.collect() as got:
        assert client.chat([{"role": "user", "content": "hi"}]) == "native hello"
    assert (got.model, got.input_tokens, got.output_tokens, got.calls) == ("gemini-test", 21, 9, 1)


# -- wiring: each stage records its usage -----------------------------------------

@pytest.fixture
def pipeline(conn, tmp_path, monkeypatch):
    from hireember import config
    from hireember.resumes import add_resume
    from p2_helpers import store_job

    config.ensure_dirs()
    path = tmp_path / "base.txt"
    path.write_text("BASE RESUME TEXT", encoding="utf-8")
    add_resume(conn, path, "Backend", "backend")
    return conn, store_job(conn, "https://j.example/usage")


def _install(monkeypatch, name, model, text, *, prompt=500, completion=100, fail=False):
    def respond(url, payload):
        if fail:
            raise RuntimeError("provider down")
        return 200, openai_body(text, prompt, completion)

    client, fake = make_llm(model, respond)
    monkeypatch.setattr(f"hireember.scoring.{name}.get_client", lambda *a, **k: client)
    return fake


def test_scoring_records_the_model_and_tokens(pipeline, monkeypatch):
    from hireember import usage
    from hireember.gating import score_job_for_ticket
    from p2_helpers import profile

    conn, url = pipeline
    _install(monkeypatch, "scorer", "score-model", "SCORE: 8\nKEYWORDS: a\nREASONING: Fits.",
             prompt=1200, completion=150)
    res = score_job_for_ticket(conn, url, profile=profile())
    assert res.status == "pending"
    got = usage.get_usage(conn, res.ticket_id)
    assert got["scoring"] == {"model": "score-model", "input_tokens": 1200, "output_tokens": 150,
                              "total_tokens": 1350}
    assert got["tailoring"] is None and got["applying"] is None


def test_tailoring_records_the_resume_and_cover_letter_calls(pipeline, monkeypatch):
    import json

    from hireember import usage
    from hireember.gating import score_job_for_ticket, tailor_ticket
    from p2_helpers import LETTER, VALID_TAILOR, profile

    conn, url = pipeline
    _install(monkeypatch, "scorer", "score-model", "SCORE: 8\nKEYWORDS: a\nREASONING: Fits.")
    res = score_job_for_ticket(conn, url, profile=profile())
    tailor_fake = _install(monkeypatch, "tailor", "tailor-model", json.dumps(VALID_TAILOR),
                           prompt=500, completion=100)
    letter_fake = _install(monkeypatch, "cover_letter", "letter-model", LETTER, prompt=500,
                           completion=100)
    out = tailor_ticket(conn, res.ticket_id, profile=profile(), validation_mode="lenient")
    assert out.status == "pending" and out.tailored_resume_path
    calls = tailor_fake.calls + letter_fake.calls
    assert calls >= 2
    got = usage.get_usage(conn, res.ticket_id)["tailoring"]
    assert got["input_tokens"] == 500 * calls and got["output_tokens"] == 100 * calls
    assert got["total_tokens"] == 600 * calls
    assert got["model"] in ("tailor-model", "letter-model")


def test_tailoring_that_fails_midway_still_records_the_tokens_spent(pipeline, monkeypatch):
    import json

    from hireember import usage
    from hireember.gating import score_job_for_ticket, tailor_ticket
    from p2_helpers import VALID_TAILOR, profile

    conn, url = pipeline
    _install(monkeypatch, "scorer", "score-model", "SCORE: 8\nKEYWORDS: a\nREASONING: Fits.")
    res = score_job_for_ticket(conn, url, profile=profile())
    tailor_fake = _install(monkeypatch, "tailor", "tailor-model", json.dumps(VALID_TAILOR),
                           prompt=500, completion=100)
    _install(monkeypatch, "cover_letter", "letter-model", "x", fail=True)
    out = tailor_ticket(conn, res.ticket_id, profile=profile(), validation_mode="lenient")
    assert out.status == "blocked for human"
    got = usage.get_usage(conn, res.ticket_id)["tailoring"]
    assert got is not None
    assert got["input_tokens"] == 500 * tailor_fake.calls and got["output_tokens"] == 100 * tailor_fake.calls


def test_scoring_without_any_model_call_leaves_no_row(pipeline, monkeypatch):
    from hireember import usage
    from hireember.gating import score_job_for_ticket
    from p2_helpers import profile

    conn, url = pipeline
    _install(monkeypatch, "scorer", "score-model", "no", fail=True)
    res = score_job_for_ticket(conn, url, profile=profile())
    assert res.status == "blocked for human"
    assert usage.get_usage(conn, res.ticket_id)["scoring"] is None


class _FakeProc:
    def __init__(self, lines):
        import io

        self.stdin = io.StringIO()
        self.stdout = iter(lines)
        self.returncode = 0
        self.pid = 0

    def wait(self, timeout=None):
        return 0

    def poll(self):
        return 0


def _applying_env(conn, tmp_path, monkeypatch, lines):
    import subprocess

    from hireember import tickets
    from hireember.apply import launcher
    from hireember.apply.session import GateSession
    from p3_helpers import add_ticket

    # The prompt text is not under test; the profile it needs is large.
    monkeypatch.setattr("hireember.apply.prompt.build_prompt", lambda **kwargs: "prompt")
    tid = add_ticket(conn, tmp_path, "ap")
    row = conn.execute("SELECT job_url FROM tickets WHERE id = ?", (tid,)).fetchone()
    job = dict(conn.execute("SELECT * FROM jobs WHERE url = ?", (row[0],)).fetchone())
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _FakeProc(lines))
    session = GateSession(conn, tid)
    tickets.get_ticket(conn, tid)
    return launcher, job, session, tid


def test_applying_records_the_model_argument_and_stream_result_tokens(conn, tmp_path, monkeypatch):
    import json

    from hireember import usage

    result_event = json.dumps({"type": "result", "result": "done",
                               "usage": {"input_tokens": 4000, "output_tokens": 600}})
    launcher, job, session, tid = _applying_env(conn, tmp_path, monkeypatch, [result_event + "\n"])
    launcher.run_job(job, 0, 0, model="sonnet-test", session=session)
    assert usage.get_usage(conn, tid)["applying"] == {"model": "sonnet-test", "input_tokens": 4000,
                                                      "output_tokens": 600, "total_tokens": 4600}


def test_applying_without_a_result_event_records_zero_tokens(conn, tmp_path, monkeypatch):
    from hireember import usage

    launcher, job, session, tid = _applying_env(conn, tmp_path, monkeypatch, [])
    launcher.run_job(job, 0, 0, model="sonnet-test", session=session)
    assert usage.get_usage(conn, tid)["applying"] == {"model": "sonnet-test", "input_tokens": 0,
                                                      "output_tokens": 0, "total_tokens": 0}


# -- ticket page and API ----------------------------------------------------------

@pytest.fixture
def web(isolated_db, tmp_path, monkeypatch):
    from p6_helpers import use_log_dir
    from hireember.database import close_connection, init_db

    use_log_dir(monkeypatch, tmp_path)
    conn = init_db()
    server, thread = start_server(isolated_db)
    yield conn, Client(server.server_address[1])
    stop_server(server, thread)
    close_connection(isolated_db)


def test_ticket_page_and_api_show_all_three_stages(web):
    from hireember import usage

    conn, client = web
    tid = make_ticket(conn, "w1")
    usage.record(conn, tid, "scoring", "claude-sonnet-5-5", 1200, 150)
    usage.record(conn, tid, "tailoring", "tailor-m", 3000, 800)
    usage.record(conn, tid, "applying", "apply-m", 12345, 678)

    status, _, body = client.request("GET", f"/tickets/{tid}")
    page = body.decode("utf-8")
    assert status == 200 and "Model and tokens" in page
    from p6_helpers import table_rows

    header = next(r for r in table_rows(page) if r and r[0] == "Stage")
    assert header == ["Stage", "Model", "Input tokens", "Output tokens", "Total tokens"]
    assert usage_row(page, "Scoring") == ["Scoring", "claude-sonnet-5-5", "1,200", "150", "1,350"]
    assert usage_row(page, "Tailoring") == ["Tailoring", "tailor-m", "3,000", "800", "3,800"]
    assert usage_row(page, "Applying") == ["Applying", "apply-m", "12,345", "678", "13,023"]

    status, data = client.get(f"/api/tickets/{tid}")
    assert status == 200
    assert data["usage"] == {
        "scoring": {"model": "claude-sonnet-5-5", "input_tokens": 1200, "output_tokens": 150,
                    "total_tokens": 1350},
        "tailoring": {"model": "tailor-m", "input_tokens": 3000, "output_tokens": 800,
                      "total_tokens": 3800},
        "applying": {"model": "apply-m", "input_tokens": 12345, "output_tokens": 678,
                     "total_tokens": 13023},
    }


def test_stage_without_a_record_shows_dashes_and_null_not_an_error(web):
    from hireember import usage

    conn, client = web
    tid = make_ticket(conn, "w2")
    usage.record(conn, tid, "scoring", "m", 10, 5)
    status, _, body = client.request("GET", f"/tickets/{tid}")
    page = body.decode("utf-8")
    assert status == 200
    assert usage_row(page, "Tailoring") == ["Tailoring", "-", "-", "-", "-"]
    assert usage_row(page, "Applying") == ["Applying", "-", "-", "-", "-"]
    status, data = client.get(f"/api/tickets/{tid}")
    assert status == 200 and data["usage"]["tailoring"] is None and data["usage"]["applying"] is None


def test_ticket_with_no_stages_run_loads_with_all_dashes(web):
    conn, client = web
    tid = make_ticket(conn, "w3")
    status, _, body = client.request("GET", f"/tickets/{tid}")
    page = body.decode("utf-8")
    assert status == 200
    for stage in ("Scoring", "Tailoring", "Applying"):
        assert usage_row(page, stage) == [stage, "-", "-", "-", "-"]
    status, data = client.get(f"/api/tickets/{tid}")
    assert status == 200 and data["usage"] == {"scoring": None, "tailoring": None, "applying": None}


def test_recorded_stage_with_zero_tokens_shows_zero_not_a_dash(web):
    from hireember import usage

    conn, client = web
    tid = make_ticket(conn, "w4")
    usage.record(conn, tid, "applying", "apply-m", 0, 0)
    page = client.request("GET", f"/tickets/{tid}")[2].decode("utf-8")
    assert usage_row(page, "Applying") == ["Applying", "apply-m", "0", "0", "0"]


def test_model_names_are_html_escaped(web):
    from hireember import usage

    conn, client = web
    tid = make_ticket(conn, "w5")
    usage.record(conn, tid, "scoring", "<b>evil</b>", 1, 1)
    page = client.request("GET", f"/tickets/{tid}")[2].decode("utf-8")
    assert "<b>evil</b>" not in page and "&lt;b&gt;evil&lt;/b&gt;" in page


def test_no_currency_cost_is_shown(web):
    from hireember import usage

    conn, client = web
    tid = make_ticket(conn, "w6")
    usage.record(conn, tid, "scoring", "m", 1000, 1000)
    page = client.request("GET", f"/tickets/{tid}?fragment=1")[2].decode("utf-8")
    assert "Model and tokens" in page and "$" not in page and "USD" not in page
