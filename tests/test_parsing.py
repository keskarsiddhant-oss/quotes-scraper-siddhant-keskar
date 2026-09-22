from pathlib import Path

from quotes_scraper.scraper import parse_page

FIXTURES = Path(__file__).parent / "fixtures"


def read(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_first_page_parses_ten_quotes_and_next_link():
    rows, next_href = parse_page(read("page1.html"), 1)
    assert len(rows) == 10
    assert next_href == "/page/2/"
    first = rows[0]
    assert first["author"] == "Albert Einstein"
    assert first["quote"].startswith("“The world as we have created it")  # curly quote kept
    assert first["tags"] == "change;deep-thoughts;thinking;world"
    assert first["page_number"] == 1


def test_last_page_has_no_next_link():
    rows, next_href = parse_page(read("page10.html"), 10)
    assert len(rows) == 10
    assert next_href is None
    assert rows[0]["page_number"] == 10


def test_quote_without_tags_gives_empty_string():
    html = ('<div class="quote"><span class="text">“q”</span>'
            '<small class="author">Bob</small><div class="tags">Tags:</div></div>')
    rows, _ = parse_page(html, 1)
    assert rows[0]["tags"] == ""
