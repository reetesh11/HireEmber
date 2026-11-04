import pytest

from hireember.web.server import ApiError, _add_urls


def test_urls_are_stripped_and_blanks_dropped():
    assert _add_urls({"urls": [" https://a.example/1 ", "", "  "]}) == ["https://a.example/1"]


@pytest.mark.parametrize("body, code", [
    ({}, "invalid_urls"),
    ({"urls": "x"}, "invalid_urls"),
    ({"urls": [1]}, "invalid_urls"),
    ({"urls": [" "]}, "invalid_urls"),
    ({"urls": [f"https://a.example/{i}" for i in range(26)]}, "too_many_urls"),
    ({"urls": ["https://a.example/" + "x" * 2048]}, "url_too_long"),
])
def test_bad_url_lists(body, code):
    with pytest.raises(ApiError) as exc:
        _add_urls(body)
    assert exc.value.code == code and exc.value.status == 400


def test_exactly_25_and_2048_are_allowed():
    url = "https://a.example/" + "x" * (2048 - len("https://a.example/"))
    assert len(_add_urls({"urls": [url] * 25})) == 25
