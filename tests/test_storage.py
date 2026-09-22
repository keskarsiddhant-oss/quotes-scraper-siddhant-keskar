import csv

import pytest

from quotes_scraper.storage import FIELDS, StorageError, identity_key, load_memory, merge, save_memory


def row(quote, author="A", tags="x", page=1):
    return {"quote": quote, "author": author, "tags": tags, "page_number": page}


def test_key_ignores_case_and_whitespace():
    assert identity_key("  Hello   World ", "Jane  Doe") == identity_key("hello world", "JANE DOE")


def test_key_ignores_page_number_and_tags():
    assert identity_key("q", "a") == identity_key("q", "a")  # key takes only quote+author


def test_key_differs_by_author():
    assert identity_key("q", "a") != identity_key("q", "b")


def test_merge_appends_only_new_and_keeps_existing_untouched():
    existing = [row("one", page=1), row("two", page=1)]
    merged, added, skipped = merge(existing, [row("TWO ", page=5), row("three", page=2)])
    assert added == 1 and skipped == 1
    assert merged[:2] == existing            # untouched, in order
    assert merged[2]["quote"] == "three"


def test_merge_dedups_within_scraped_batch():
    merged, added, skipped = merge([], [row("a"), row("a"), row("b")])
    assert (len(merged), added, skipped) == (2, 2, 1)


def test_load_missing_file_is_empty(tmp_path):
    assert load_memory(tmp_path / "nope.csv") == []


def test_save_load_roundtrip_preserves_unicode(tmp_path):
    path = tmp_path / "sub" / "memory.csv"   # parent directory is created
    rows = [row("“Curly” – café", "André", "a;b", 3)]
    save_memory(path, rows)
    with open(path, newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == FIELDS
    loaded = load_memory(path)
    assert loaded[0]["quote"] == "“Curly” – café"
    assert loaded[0]["page_number"] == "3"
    assert not list(path.parent.glob("*.tmp"))  # no temp files left behind


def test_wrong_header_raises(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(StorageError):
        load_memory(path)
