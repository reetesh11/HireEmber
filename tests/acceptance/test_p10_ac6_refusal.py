"""Phase 10 AC-6: non-http schemes and private or local addresses are refused before any body is read."""

import httpx
import pytest

from p10_helpers import no_extract, public_resolver, resolver_for, job_count

OWN = "This address is on your own network or computer, so it was not fetched."
SCHEME = "Only http and https links are supported."
BAD_ADDRS = ["127.0.0.1", "127.8.9.1", "10.1.2.3", "192.168.1.5", "172.16.0.1", "172.31.255.254",
             "169.254.169.254", "0.0.0.0", "::1", "fe80::1", "fc00::1", "fd12:3456::1", "::", "224.0.0.1"]


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)",
                                 "gopher://example.com/"])
def test_check_url_refuses_other_schemes(url):
    from hireember.urlfetch import check_url

    assert check_url(url, resolver=public_resolver) == SCHEME


def test_check_url_no_host():
    from hireember.urlfetch import check_url

    assert check_url("http:///path", resolver=public_resolver) == "That is not a valid web address."


@pytest.mark.parametrize("host", ["localhost", "app.localhost", "LOCALHOST"])
def test_check_url_refuses_localhost_names(host):
    from hireember.urlfetch import check_url

    assert check_url(f"http://{host}:8765/", resolver=resolver_for({host: ["127.0.0.1"]})) == OWN


@pytest.mark.parametrize("ip", BAD_ADDRS)
def test_check_url_refuses_ip_literals(ip):
    from hireember.urlfetch import check_url

    host = f"[{ip}]" if ":" in ip else ip
    assert check_url(f"http://{host}/", resolver=resolver_for({ip: [ip], host: [ip]})) == OWN


@pytest.mark.parametrize("ip", BAD_ADDRS[:8])
def test_check_url_refuses_names_that_resolve_to_private(ip):
    from hireember.urlfetch import check_url

    assert check_url("https://sneaky.example/", resolver=resolver_for({"sneaky.example": [ip]})) == OWN


def test_check_url_checks_every_resolved_address():
    from hireember.urlfetch import check_url

    res = resolver_for({"mixed.example": ["93.184.216.34", "10.0.0.5"]})
    assert check_url("https://mixed.example/", resolver=res) == OWN


def test_check_url_allows_public():
    from hireember.urlfetch import check_url

    assert check_url("https://example.com/jobs/1", resolver=public_resolver) is None
    assert check_url("https://example.com/", resolver=resolver_for({"example.com": ["2606:2800:220:1::1"]})) is None


def test_redirect_to_private_address_is_refused_without_a_second_request():
    from hireember.urlfetch import FetchError, fetch_page

    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest/meta-data"})

    with pytest.raises(FetchError) as exc:
        fetch_page("https://example.com/a", transport=httpx.MockTransport(handler), resolver=public_resolver)
    assert exc.value.refused is True and exc.value.reason == OWN
    assert seen == ["https://example.com/a"]


def test_redirect_to_localhost_name_is_refused():
    from hireember.urlfetch import FetchError, fetch_page

    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(301, headers={"Location": "http://localhost:8765/admin"})
        raise AssertionError("must not be requested")

    with pytest.raises(FetchError) as exc:
        fetch_page("https://example.com/a", transport=httpx.MockTransport(handler), resolver=public_resolver)
    assert exc.value.refused is True


def test_fetch_page_refuses_scheme_before_any_request():
    from hireember.urlfetch import FetchError, fetch_page

    def handler(request):
        raise AssertionError("no request may be made")

    with pytest.raises(FetchError) as exc:
        fetch_page("ftp://example.com/x", transport=httpx.MockTransport(handler), resolver=public_resolver)
    assert exc.value.refused is True and exc.value.reason == SCHEME


def test_too_many_redirects_is_a_plain_failure():
    from hireember.urlfetch import FetchError, fetch_page

    def handler(request):
        return httpx.Response(302, headers={"Location": "https://example.com/loop"})

    with pytest.raises(FetchError) as exc:
        fetch_page("https://example.com/loop", transport=httpx.MockTransport(handler), resolver=public_resolver)
    assert exc.value.reason == "The page could not be fetched."


def test_localhost_url_fails_with_reason_and_no_network(conn):
    from hireember.addjob import add_job_from_url

    result = add_job_from_url(conn, "http://localhost:8765/", extract=no_extract)
    assert result.status == "failed" and result.reason == OWN


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://10.0.0.1/x", "http://192.168.0.9/", "http://[::1]/",
                                 "http://169.254.169.254/latest"])
def test_private_literals_fail_with_blocked_ticket(conn, url):
    from hireember import tickets
    from hireember.addjob import add_job_from_url

    result = add_job_from_url(conn, url, extract=no_extract)
    assert result.status == "failed" and result.reason == OWN
    assert isinstance(result.ticket_id, int)
    t = tickets.get_ticket(conn, result.ticket_id)
    assert t["status"] == "blocked for human" and t["status_reason"] == OWN


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x"])
def test_other_schemes_fail_without_ticket(conn, url):
    from hireember.addjob import add_job_from_url

    result = add_job_from_url(conn, url, extract=no_extract)
    assert result.status == "failed" and result.reason == SCHEME and result.ticket_id is None
    assert job_count(conn) == 0
