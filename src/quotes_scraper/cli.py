"""Argument parsing, orchestration and exit codes."""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from quotes_scraper import __version__
from quotes_scraper.auth import login
from quotes_scraper.scraper import TIMEOUT_MS, ScraperError, scrape_all
from quotes_scraper.storage import StorageError, load_memory, merge, save_memory

# Built with Path (not the string "data/memory.csv") so the --help text shows
# the OS-native separator ("data\memory.csv" on Windows, "data/memory.csv" elsewhere).
DEFAULT_MEMORY_FILE = Path("data") / "memory.csv"

log = logging.getLogger("quotes_scraper")


def build_parser():
    # Options shared by both subcommands live on a parent parser.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run the browser without a visible window (default). "
        "Use --no-headless to watch the browser.",
    )
    common.add_argument(
        "--memory-file",
        default=DEFAULT_MEMORY_FILE,
        metavar="PATH",
        help="CSV file used as output and memory (default: %(default)s).",
    )

    parser = argparse.ArgumentParser(
        prog="quotes-scraper",
        description="Scrape quotes.toscrape.com (after logging in) into a CSV memory file.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="{backfill,latest}")
    sub.add_parser(
        "backfill", parents=[common],
        help="Scrape every page and merge the quotes into the memory file.",
        description="Log in, scrape all pages and merge the results into the memory file "
        "without creating duplicates.",
    )
    sub.add_parser(
        "latest", parents=[common],
        help="Scrape every page and append only quotes not already in memory.",
        description="Log in, scrape all pages and append only quotes that are not yet in "
        "the memory file. Existing rows are never modified.",
    )
    return parser


def get_credentials():
    # usecwd=True: look for .env from the directory the user runs the command in
    # (the default would search from inside the installed package).
    load_dotenv(find_dotenv(usecwd=True))
    username = os.environ.get("QUOTES_USERNAME", "").strip()
    password = os.environ.get("QUOTES_PASSWORD", "")
    if not username or not password:
        raise ScraperError(
            "Missing credentials. Set QUOTES_USERNAME and QUOTES_PASSWORD in a .env file "
            "(copy .env.example to .env) or in your environment."
        )
    return username, password


def fetch_quotes(headless, username, password):
    """Launch the browser, log in (mandatory) and scrape every page."""
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=headless)
        except PlaywrightError as exc:
            if "playwright install" in str(exc) or "Executable doesn't exist" in str(exc):
                raise ScraperError(
                    "Chromium is not installed for Playwright. "
                    "Run this once, then try again:  playwright install chromium"
                ) from exc
            raise ScraperError(f"Could not start the browser: {str(exc).splitlines()[0]}") from exc
        try:
            page = browser.new_page()
            page.set_default_timeout(TIMEOUT_MS)
            login(page, username, password)
            return scrape_all(page)
        finally:
            browser.close()


def run(args):
    username, password = get_credentials()  # fail before starting a browser
    # args.memory_file is a Path when the default was used, or a plain str when the
    # user passed --memory-file; wrap in Path so the rest of the code has one type.
    memory_path = Path(args.memory_file)

    # Load memory first so an unreadable/invalid file fails before we spend time scraping.
    if memory_path.exists():
        existing = load_memory(memory_path)
    else:
        existing = []
        if args.command == "latest":
            print(f"Memory file {memory_path} not found; starting with empty memory.")

    scraped = fetch_quotes(args.headless, username, password)

    merged, added, skipped = merge(existing, scraped)

    if args.command == "latest" and added == 0:
        print("No new quotes found.")
        return 0

    save_memory(memory_path, merged)
    if args.command == "latest":
        print(f"Added {added} new quote(s) to {memory_path}.")
    else:
        print(
            f"Backfill complete: {len(scraped)} quotes found on the site, "
            f"{added} added, {skipped} skipped as duplicates. Memory file: {memory_path}"
        )
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        return run(args)
    except (ScraperError, StorageError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
