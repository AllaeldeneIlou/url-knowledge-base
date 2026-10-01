from pathlib import Path

from url_kb.ingest.parser import (
    parse_master_url_database_csv,
    parse_notion_url_export_csv,
    parse_url_csv,
)


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


def test_parse_url_csv_preserves_optional_row_metadata(tmp_path: Path):
    csv_path = tmp_path / "urls.csv"
    csv_path.write_text(
        "url,title,source_type,status\n"
        "https://example.com,Example Title,documentation,IMPORTED\n",
        encoding="utf-8",
    )

    result = parse_url_csv(csv_path)

    assert result.records[0].row_number == 2
    assert result.records[0].normalized_url.canonical_url == "https://example.com/"
    assert result.records[0].original_label == "Example Title"
    assert result.records[0].source_type == "documentation"
    assert result.records[0].raw_imported_status == "IMPORTED"
    assert result.valid[0].canonical_url == "https://example.com/"


def test_parse_master_url_database_csv_preserves_real_corpus_metadata(tmp_path: Path):
    csv_path = tmp_path / "master_url_database.csv"
    csv_path.write_text(
        "id,raw_url,clean_url,domain,source_file,date_added,macro_area,"
        "subtopic,source_type,technical_depth,strategic_relevance,status,notes\n"
        "1,https://example.com/cloud?b=2&a=1,https://example.com/cloud,"
        "example.com,seed.txt,2026-01-01,Cloud,,documentation,,,TO_REVIEW,\n",
        encoding="utf-8",
    )

    result = parse_master_url_database_csv(csv_path)

    assert result.records[0].normalized_url.canonical_url == "https://example.com/cloud?a=1&b=2"
    assert result.records[0].original_label is None
    assert result.records[0].source_type == "documentation"
    assert result.records[0].raw_imported_status == "TO_REVIEW"
    assert result.records[0].source_section == "Cloud"
    assert result.records[0].source_format == "csv_master_url_database"


def test_parse_notion_url_export_csv_preserves_real_corpus_metadata(tmp_path: Path):
    csv_path = tmp_path / "notion_second_brain_links.csv"
    csv_path.write_text(
        "Name,URL,Domain,Root Domain,Site Group,URL Pattern,PARA,Project,Area,"
        "Resource,Topic,Source Type,Content Format,Content Bucket,Status,"
        "CODE Stage,Review Queue,Review Priority\n"
        "Kubernetes Guide,https://kubernetes.io/docs/home/,kubernetes.io,"
        "kubernetes.io,kubernetes,docs,Resource,,Cloud,,Kubernetes,"
        "documentation,guide,Infrastructure,TO_REVIEW,,High Priority,P1\n",
        encoding="utf-8",
    )

    result = parse_notion_url_export_csv(csv_path)

    assert result.records[0].normalized_url.canonical_url == "https://kubernetes.io/docs/home/"
    assert result.records[0].original_label == "Kubernetes Guide"
    assert result.records[0].source_type == "documentation"
    assert result.records[0].raw_imported_status == "TO_REVIEW"
    assert result.records[0].source_section == "High Priority"
    assert result.records[0].source_format == "csv_url_export"
