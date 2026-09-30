from url_kb.ingest.dedupe import dedupe_normalized
from url_kb.ingest.normalize import normalize_url


def test_dedupe_normalized_keeps_first_seen_canonical_url():
    first = normalize_url("https://docs.python.org/3/library/urllib.parse.html")
    duplicate = normalize_url("https://docs.python.org:443/3/library/urllib.parse.html#url-parsing")
    other = normalize_url("https://docs.pytest.org/en/stable/")

    result = dedupe_normalized([first, duplicate, other])

    assert result == [first, other]
