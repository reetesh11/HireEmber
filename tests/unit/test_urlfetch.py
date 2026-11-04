import httpx
import pytest

from hireember.urlfetch import FetchError, check_url, fetch_page


def public(host, port, *a, **k):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


def test_check_url_ipv4_mapped_private_refused():
    assert check_url("http://[::ffff:10.0.0.1]/", resolver=public)


def test_check_url_unresolvable_name_is_left_to_fetch():
    def fail(*a, **k):
        raise OSError("no dns")

    assert check_url("https://nope.example/", resolver=fail) is None


def test_redirect_to_public_host_is_followed():
    def handler(request):
        if request.url.path == "/a":
            return httpx.Response(302, headers={"Location": "/b"})
        return httpx.Response(200, text="ok")

    res = fetch_page("https://example.com/a", transport=httpx.MockTransport(handler), resolver=public)
    assert res.url == "https://example.com/b" and res.html == "ok"


def test_connection_error_is_plain():
    def handler(request):
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(FetchError) as exc:
        fetch_page("https://example.com/a", transport=httpx.MockTransport(handler), resolver=public)
    assert exc.value.reason == "The page could not be fetched."
