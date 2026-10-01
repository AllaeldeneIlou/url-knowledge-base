from pathlib import Path

from url_kb.ingest.parser import (
    parse_bare_or_mixed_url_text,
    parse_logseq_markdown_blocks,
    parse_markdown_links,
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


def test_parse_markdown_links_preserves_label_heading_and_line_number(tmp_path: Path):
    markdown_path = tmp_path / "links.md"
    markdown_path.write_text(
        "# Cloud\n"
        "See [Example Guide](https://example.com/guide?b=2&a=1).\n",
        encoding="utf-8",
    )

    result = parse_markdown_links(markdown_path)

    assert len(result.records) == 1
    assert result.records[0].row_number == 2
    assert result.records[0].normalized_url.canonical_url == "https://example.com/guide?a=1&b=2"
    assert result.records[0].original_label == "Example Guide"
    assert result.records[0].source_section == "Cloud"
    assert result.records[0].source_format == "markdown_links"


def test_parse_markdown_links_supports_multiple_links_and_ignores_images(tmp_path: Path):
    markdown_path = tmp_path / "links.md"
    markdown_path.write_text(
        "![Alt](https://images.example.com/image.png) "
        "[One](https://one.example.com) [Two](https://two.example.com/path)\n",
        encoding="utf-8",
    )

    result = parse_markdown_links(markdown_path)

    assert [record.original_label for record in result.records] == ["One", "Two"]
    assert [record.normalized_url.domain for record in result.records] == [
        "one.example.com",
        "two.example.com",
    ]
    assert [record.block_number for record in result.records] == [1, 2]


def test_parse_logseq_markdown_blocks_preserves_type_and_status_properties(tmp_path: Path):
    markdown_path = tmp_path / "logseq.md"
    markdown_path.write_text(
        "# Review Queue\n"
        "- [Architecture Note](https://example.com/architecture)\n"
        "  type:: documentation\n"
        "  status:: TO_REVIEW\n",
        encoding="utf-8",
    )

    result = parse_logseq_markdown_blocks(markdown_path)

    assert len(result.records) == 1
    assert result.records[0].original_label == "Architecture Note"
    assert result.records[0].source_type == "documentation"
    assert result.records[0].raw_imported_status == "TO_REVIEW"
    assert result.records[0].source_section == "Review Queue"
    assert result.records[0].source_format == "logseq_markdown_blocks"


def test_parse_bare_or_mixed_url_text_extracts_urls_and_strips_trailing_punctuation(
    tmp_path: Path,
):
    text_path = tmp_path / "urls_AI-Agents.txt"
    text_path.write_text(
        "Useful: https://example.com/one, and https://example.org/two).\n",
        encoding="utf-8",
    )

    result = parse_bare_or_mixed_url_text(text_path)

    assert [record.normalized_url.canonical_url for record in result.records] == [
        "https://example.com/one",
        "https://example.org/two",
    ]
    assert [record.block_number for record in result.records] == [1, 2]
    assert {record.source_section for record in result.records} == {"urls_AI-Agents"}
    assert {record.source_format for record in result.records} == {"bare_or_mixed_url_text"}


def test_text_parsers_collect_malformed_urls_without_failing_batch(tmp_path: Path):
    text_path = tmp_path / "mixed.txt"
    text_path.write_text(
        "Unsupported file://localhost/private and valid https://example.com.\n",
        encoding="utf-8",
    )

    result = parse_bare_or_mixed_url_text(text_path)

    assert len(result.records) == 1
    assert len(result.errors) == 1
    assert result.errors[0].row_number == 1
    assert result.errors[0].raw_url == "file://localhost/private"
    assert result.errors[0].reason == "URL must use http or https"
