from pathlib import Path

from url_kb.ingest.service import ingest_batch, ingest_private_corpus_csvs
from url_kb.storage.sqlite_repo import SQLiteURLRepository


def test_ingest_batch_records_counts_and_malformed_rows(tmp_path: Path):
    csv_path = tmp_path / "urls.csv"
    csv_path.write_text(
        "url,title\n"
        "https://example.com/path#fragment,Example\n"
        "https://example.com/path,Duplicate\n"
        "not a url,Bad row\n"
        "https://docs.python.org/3/,Python\n",
        encoding="utf-8",
    )
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    result = ingest_batch(csv_path, repository)

    assert result.input_count == 4
    assert result.valid_count == 3
    assert result.inserted_count == 2
    assert result.duplicate_count == 1
    assert result.malformed_count == 1
    assert result.failed_count == 1
    assert result.status == "completed_with_errors"
    assert result.errors[0].row_number == 4
    assert repository.count_url_records() == 2
    assert repository.count_source_occurrences() == 3

    runs = repository.list_ingest_runs()
    assert len(runs) == 1
    assert runs[0].run_id == result.run_id
    assert runs[0].input_count == 4
    assert runs[0].inserted_count == 2
    assert runs[0].duplicate_count == 1
    assert runs[0].failed_count == 1

    records = repository.list_url_records()
    example_record = next(record for record in records if record.domain == "example.com")
    assert example_record.title == "Example"
    assert example_record.original_label == "Example"
    assert example_record.source_type is None
    assert example_record.raw_imported_status is None


def test_ingest_batch_skips_duplicates_already_in_database(tmp_path: Path):
    first_csv = tmp_path / "first.csv"
    first_csv.write_text("url\nhttps://example.com/path\n", encoding="utf-8")
    second_csv = tmp_path / "second.csv"
    second_csv.write_text(
        "url\n"
        "https://example.com/path#fragment\n"
        "https://example.org/other\n",
        encoding="utf-8",
    )
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    first_result = ingest_batch(first_csv, repository)
    second_result = ingest_batch(second_csv, repository)

    assert first_result.inserted_count == 1
    assert second_result.inserted_count == 1
    assert second_result.duplicate_count == 1
    assert second_result.failed_count == 0
    assert repository.count_url_records() == 2


def test_ingest_batch_does_not_duplicate_source_occurrences_on_reingest(tmp_path: Path):
    csv_path = tmp_path / "urls.csv"
    csv_path.write_text(
        "url,title\n"
        "https://example.com/path#fragment,Example\n"
        "https://example.com/path,Duplicate occurrence\n"
        "https://example.org/other,Other\n",
        encoding="utf-8",
    )
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    first_result = ingest_batch(csv_path, repository)
    first_occurrence_count = repository.count_source_occurrences()
    second_result = ingest_batch(csv_path, repository)

    assert first_result.inserted_count == 2
    assert first_result.duplicate_count == 1
    assert first_occurrence_count == 3
    assert second_result.inserted_count == 0
    assert second_result.duplicate_count == 3
    assert repository.count_url_records() == 2
    assert repository.count_source_occurrences() == first_occurrence_count


def test_ingest_private_corpus_csvs_imports_supported_real_corpus_profiles(
    tmp_path: Path,
):
    corpus_path = tmp_path / "corpus"
    corpus_path.mkdir()
    (corpus_path / "master_url_database.csv").write_text(
        "id,raw_url,clean_url,domain,source_file,date_added,macro_area,"
        "subtopic,source_type,technical_depth,strategic_relevance,status,notes\n"
        "1,https://example.com/cloud,https://example.com/cloud,"
        "example.com,seed.txt,2026-01-01,Cloud,,documentation,,,TO_REVIEW,\n"
        "2,not a url,,example.com,seed.txt,2026-01-01,Cloud,,documentation,,,TO_REVIEW,\n",
        encoding="utf-8",
    )
    (corpus_path / "notion_second_brain_links.csv").write_text(
        "Name,URL,Domain,Root Domain,Site Group,URL Pattern,PARA,Project,Area,"
        "Resource,Topic,Source Type,Content Format,Content Bucket,Status,"
        "CODE Stage,Review Queue,Review Priority\n"
        "Cloud Duplicate,https://example.com/cloud,example.com,example.com,"
        "example,docs,Resource,,Cloud,,Cloud,documentation,guide,"
        "Infrastructure,TO_REVIEW,,Review Queue,P1\n"
        "Kubernetes Guide,https://kubernetes.io/docs/home/,kubernetes.io,"
        "kubernetes.io,kubernetes,docs,Resource,,Cloud,,Kubernetes,"
        "documentation,guide,Infrastructure,TO_REVIEW,,Review Queue,P1\n",
        encoding="utf-8",
    )
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    result = ingest_private_corpus_csvs(corpus_path, repository)

    assert result.input_count == 4
    assert result.valid_count == 3
    assert result.inserted_count == 2
    assert result.duplicate_count == 1
    assert result.failed_count == 1
    assert repository.count_url_records() == 2
    assert repository.count_source_occurrences() == 3
    assert result.files[0].error_reasons == {"URL must use http or https": 1}

    occurrences = repository.list_source_occurrences()
    assert {occurrence.source_format for occurrence in occurrences} == {
        "csv_master_url_database",
        "csv_url_export",
    }
    assert any(occurrence.source_section == "Cloud" for occurrence in occurrences)
    assert any(occurrence.source_section == "Review Queue" for occurrence in occurrences)


def test_ingest_private_corpus_csvs_can_select_one_profile(tmp_path: Path):
    corpus_path = tmp_path / "corpus"
    corpus_path.mkdir()
    (corpus_path / "master_url_database.csv").write_text(
        "id,raw_url,clean_url,domain,source_file,date_added,macro_area,"
        "subtopic,source_type,technical_depth,strategic_relevance,status,notes\n"
        "1,https://example.com/cloud,https://example.com/cloud,"
        "example.com,seed.txt,2026-01-01,Cloud,,documentation,,,TO_REVIEW,\n",
        encoding="utf-8",
    )
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    result = ingest_private_corpus_csvs(corpus_path, repository, profiles=["master_csv"])

    assert result.input_count == 1
    assert result.inserted_count == 1
    assert result.files[0].profile == "master_csv"


def test_ingest_private_corpus_markdown_profile_preserves_occurrences(
    tmp_path: Path,
):
    corpus_path = tmp_path / "corpus"
    markdown_path = (
        corpus_path
        / "not_sorted"
        / "urls_20260715"
        / "urls_20260715_deduplicati.md"
    )
    markdown_path.parent.mkdir(parents=True)
    markdown_path.write_text(
        "# Cloud\n"
        "- [Example Guide](https://example.com/guide)\n"
        "- [Other Guide](https://example.org/other)\n",
        encoding="utf-8",
    )
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    result = ingest_private_corpus_csvs(corpus_path, repository, profiles=["markdown_links"])

    assert result.input_count == 2
    assert result.inserted_count == 2
    assert result.failed_count == 0
    assert result.files[0].profile == "markdown_links"
    assert result.files[0].source_file == str(markdown_path)

    occurrences = repository.list_source_occurrences()
    assert len(occurrences) == 2
    assert {occurrence.source_format for occurrence in occurrences} == {"markdown_links"}
    assert {occurrence.source_section for occurrence in occurrences} == {"Cloud"}
    assert {occurrence.row_number for occurrence in occurrences} == {2, 3}
    assert {occurrence.original_label for occurrence in occurrences} == {
        "Example Guide",
        "Other Guide",
    }


def test_private_non_csv_source_occurrences_are_idempotent_on_reingest(tmp_path: Path):
    corpus_path = tmp_path / "corpus"
    markdown_path = (
        corpus_path
        / "not_sorted"
        / "urls_20260716"
        / "urls_20260716_deduplicati.md"
    )
    markdown_path.parent.mkdir(parents=True)
    markdown_path.write_text(
        "# Tools\n"
        "- [Example Guide](https://example.com/guide)\n"
        "- [Other Guide](https://example.org/other)\n",
        encoding="utf-8",
    )
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    first_result = ingest_private_corpus_csvs(
        corpus_path,
        repository,
        profiles=["markdown_links"],
    )
    first_occurrence_count = repository.count_source_occurrences()
    second_result = ingest_private_corpus_csvs(
        corpus_path,
        repository,
        profiles=["markdown_links"],
    )

    assert first_result.inserted_count == 2
    assert second_result.inserted_count == 0
    assert second_result.duplicate_count == 2
    assert repository.count_url_records() == 2
    assert repository.count_source_occurrences() == first_occurrence_count


def test_private_same_line_duplicate_url_occurrences_are_preserved_and_idempotent(
    tmp_path: Path,
):
    corpus_path = tmp_path / "corpus"
    bare_path = corpus_path / "not_sorted" / "20260422_urls" / "urls_AI-Agents.txt"
    bare_path.parent.mkdir(parents=True)
    bare_path.write_text(
        "Repeated https://example.com/repeated and https://example.com/repeated\n",
        encoding="utf-8",
    )
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    first_result = ingest_private_corpus_csvs(
        corpus_path,
        repository,
        profiles=["bare_or_mixed_url_text"],
    )
    first_occurrence_count = repository.count_source_occurrences()
    second_result = ingest_private_corpus_csvs(
        corpus_path,
        repository,
        profiles=["bare_or_mixed_url_text"],
    )

    assert first_result.valid_count == 2
    assert first_result.inserted_count == 1
    assert first_result.duplicate_count == 1
    assert first_occurrence_count == 2
    assert second_result.inserted_count == 0
    assert second_result.duplicate_count == 2
    assert repository.count_source_occurrences() == first_occurrence_count
    assert {occurrence.block_number for occurrence in repository.list_source_occurrences()} == {
        1,
        2,
    }


def test_ingest_private_corpus_logseq_and_bare_profiles(tmp_path: Path):
    corpus_path = tmp_path / "corpus"
    logseq_path = (
        corpus_path
        / "not_sorted"
        / "markdown_urls"
        / "python-engineering.md"
    )
    bare_path = corpus_path / "not_sorted" / "20260422_urls" / "urls_AI-Agents.txt"
    logseq_path.parent.mkdir(parents=True)
    bare_path.parent.mkdir(parents=True)
    logseq_path.write_text(
        "# Python\n"
        "- [Python Docs](https://docs.example.com/python)\n"
        "  type:: documentation\n",
        encoding="utf-8",
    )
    bare_path.write_text(
        "Read https://agents.example.com/overview.\n",
        encoding="utf-8",
    )
    repository = SQLiteURLRepository(tmp_path / "url_kb.sqlite3")

    result = ingest_private_corpus_csvs(
        corpus_path,
        repository,
        profiles=["logseq_markdown_blocks", "bare_or_mixed_url_text"],
    )

    assert result.input_count == 2
    assert result.inserted_count == 2
    assert {file_summary.profile for file_summary in result.files} == {
        "logseq_markdown_blocks",
        "bare_or_mixed_url_text",
    }
    occurrences = repository.list_source_occurrences()
    assert {occurrence.source_format for occurrence in occurrences} == {
        "logseq_markdown_blocks",
        "bare_or_mixed_url_text",
    }
    assert any(occurrence.original_label == "Python Docs" for occurrence in occurrences)
    records = repository.list_url_records()
    assert any(record.source_type == "documentation" for record in records)
