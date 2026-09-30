import pytest

from url_kb.ingest.normalize import InvalidURLError, normalize_url


def test_normalize_url_lowercases_scheme_and_domain_removes_fragment_and_default_port():
    result = normalize_url("HTTPS://Docs.Python.org:443/3/library/urllib.parse.html#url-parsing")

    assert result.canonical_url == "https://docs.python.org/3/library/urllib.parse.html"
    assert result.domain == "docs.python.org"
    assert len(result.url_hash) == 64


def test_normalize_url_sorts_query_parameters():
    result = normalize_url("https://example.com/search?b=2&a=1")

    assert result.canonical_url == "https://example.com/search?a=1&b=2"


@pytest.mark.parametrize(
    "raw_url",
    [
        "",
        "not a url",
        "ftp://example.com/file.txt",
        "https:///missing-host",
        "https://bad host.example/path",
    ],
)
def test_normalize_url_rejects_malformed_or_unsupported_values(raw_url):
    with pytest.raises(InvalidURLError):
        normalize_url(raw_url)
