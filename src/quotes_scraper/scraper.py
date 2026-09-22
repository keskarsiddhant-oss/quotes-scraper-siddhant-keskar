"""Page iteration and HTML parsing."""

import logging
import time
from html.parser import HTMLParser
from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightError

BASE_URL = "https://quotes.toscrape.com"
TIMEOUT_MS = 15_000  # per-navigation / per-action timeout
RETRIES = 3          # attempts per navigation
BACKOFF_S = 2        # wait 2s, then 4s, ... between attempts

log = logging.getLogger(__name__)


class ScraperError(Exception):
    """An expected failure (network, login, ...) with a user-readable message."""


def goto_with_retry(page, url):
    """Navigate to `url`, retrying with exponential backoff on failure."""
    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            response = page.goto(url, timeout=TIMEOUT_MS)
            if response is not None and response.status >= 400:
                raise ScraperError(f"{url} returned HTTP {response.status}")
            return
        except (PlaywrightError, ScraperError) as exc:
            last_error = exc
            if attempt < RETRIES:
                wait = BACKOFF_S * 2 ** (attempt - 1)
                log.warning("Attempt %d/%d for %s failed; retrying in %ds", attempt, RETRIES, url, wait)
                time.sleep(wait)
    # Keep only the first line of Playwright's verbose message (it includes a call log).
    reason = str(last_error).strip().splitlines()[0]
    raise ScraperError(f"Could not load {url} after {RETRIES} attempts: {reason}")


class _QuotesParser(HTMLParser):
    """Collects quotes and the 'Next' link from one page of HTML.

    Uses the standard library so the package needs no extra dependency.
    """

    def __init__(self):
        super().__init__()
        self.quotes = []        # list of dicts: quote, author, tags (list)
        self.next_href = None
        self._current = None    # quote being built
        self._field = None      # "quote" / "author" / "tag" while inside that element
        self._buf = []
        self._in_next = False

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        if tag == "div" and "quote" in classes:
            self._current = {"quote": "", "author": "", "tags": []}
            self.quotes.append(self._current)  # filled in as we parse its children
        elif tag == "li" and "next" in classes:
            self._in_next = True
        elif tag == "a" and self._in_next:
            self.next_href = dict(attrs).get("href")
        elif self._current is not None:
            if tag == "span" and "text" in classes:
                self._field = "quote"
            elif tag == "small" and "author" in classes:
                self._field = "author"
            elif tag == "a" and "tag" in classes:
                self._field = "tag"
            if self._field:
                self._buf = []

    def handle_data(self, data):
        if self._field:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "li":
            self._in_next = False
        if not self._field or self._current is None:
            return
        text = "".join(self._buf).strip()
        if self._field == "tag":
            self._current["tags"].append(text)
        else:
            self._current[self._field] = text
        self._field = None


def parse_page(html, page_number):
    """Parse one page of HTML. Returns (rows, next_href_or_None).

    Each row is a dict with the CSV fields; tags are joined with ';'.
    """
    parser = _QuotesParser()
    parser.feed(html)
    parser.close()
    rows = []
    for q in parser.quotes:
        rows.append({
            "quote": q["quote"],
            "author": q["author"],
            "tags": ";".join(q["tags"]),
            "page_number": page_number,
        })
    return rows, parser.next_href


def scrape_all(page):
    """Follow the 'Next' link from page 1 until there is none. Returns all rows."""
    all_rows = []
    url = BASE_URL + "/"
    page_number = 1
    while url:
        goto_with_retry(page, url)
        rows, next_href = parse_page(page.content(), page_number)
        log.info("Page %d: %d quotes", page_number, len(rows))
        all_rows.extend(rows)
        url = urljoin(url, next_href) if next_href else None
        page_number += 1
    return all_rows
