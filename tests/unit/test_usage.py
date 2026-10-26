"""Usage store, collector and LLM hook."""

import httpx

from hireember import usage
from hireember.database import init_db
from hireember.llm import LLMClient


def test_record_sums_and_get_usage(isolated_db):
    conn = init_db()
    usage.record(conn, 1, "scoring", "a", 10, 2)
    usage.record(conn, 1, "scoring", "b", 5, 1)
    assert usage.get_usage(conn, 1)["scoring"] == {
        "model": "b", "input_tokens": 15, "output_tokens": 3, "total_tokens": 18}
    assert usage.get_usage(conn, 2)["tailoring"] is None


def test_collect_nests_and_reset():
    with usage.collect() as outer:
        usage.note_call("m", 1, 1)
        with usage.collect() as inner:
            usage.note_call("n", 2, 2)
        usage.note_call("m", 1, 1)
    assert (outer.calls, outer.input_tokens, inner.calls) == (2, 2, 1)


class _Http:
    def __init__(self, body):
        self.body = body

    def post(self, url, **kwargs):
        return httpx.Response(200, json=self.body, request=httpx.Request("POST", url))


def test_llm_reports_usage_and_missing_is_zero():
    client = LLMClient("http://localhost:1/v1", "m", "")
    client._client = _Http({"choices": [{"message": {"content": "hi"}}],
                            "usage": {"prompt_tokens": 3, "completion_tokens": 4}})
    with usage.collect() as got:
        assert client.chat([{"role": "user", "content": "x"}]) == "hi"
    assert (got.input_tokens, got.output_tokens) == (3, 4)
    client._client = _Http({"choices": [{"message": {"content": "hi"}}]})
    with usage.collect() as got:
        client.chat([{"role": "user", "content": "x"}])
    assert (got.input_tokens, got.output_tokens, got.calls) == (0, 0, 1)
