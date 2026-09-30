from pathlib import Path

from url_kb.ingest.parser import parse_url_csv


def test_parse_url_csv_collects_malformed_rows_without_failing_batch(tmp_path: Path):
    csv_path = tmp_path / "urls.csv"
    csv_path.write_text(
        "url,title\n"
        "https://example.com,Example\n"
        "not a url,Bad\n"
        "https://example.com/path#fragment,Example path\n",
        encoding="utf-8",
    )

    result = parse_url_csv(csv_path)

    assert [item.canonical_url for item in result.valid] == [
        "https://example.com/",
        "https://example.com/path",
    ]
    assert len(result.errors) == 1
    assert result.errors[0].row_number == 3
    assert result.errors[0].raw_url == "not a url"
