# quotes-scraper

A small command-line tool that logs in to <https://quotes.toscrape.com>, scrapes every quote
and keeps them in a CSV file that doubles as the scraper's memory.

## Architecture

| Module | Responsibility |
| --- | --- |
| `cli.py` | Argument parsing (`argparse`), orchestration, error handling, exit codes |
| `auth.py` | Logs in through the real login form (Playwright) and verifies the "Logout" link |
| `scraper.py` | Navigation with timeouts/retry/backoff, page iteration via the "Next" link, HTML parsing (stdlib `html.parser`) |
| `storage.py` | CSV load/save (atomic write), duplicate key, merge |

Flow: read credentials from `.env` → launch Chromium → log in (abort on failure) → scrape all
pages → merge with the CSV → write the CSV.

## Assumptions, limitations and trade-offs

- Uses **Chromium via Playwright**; the browser binary is a separate one-time download (see install steps).
- Developed and **run and verified only on macOS (Apple Silicon), Python 3.9**.
- The code is **written to be Windows-compatible** and was reviewed with that in mind: all file
  paths go through `pathlib.Path` (no hardcoded `/` separators), every `open()` call passes
  `encoding="utf-8"` explicitly (Windows would otherwise default to cp1252/the system locale
  encoding, which corrupts the curly quotes in the scraped data), the CSV is written with
  `newline=""` (Windows otherwise adds `\r\n` on top of the `csv` module's own line endings,
  producing blank rows on read-back), and Playwright's Python API and `playwright install
  chromium` are cross-platform with no hardcoded browser path. There is no shelling out
  (`subprocess`/`os.system`) anywhere in the codebase, so there are no Unix-shell assumptions to
  worry about. That said, **Windows behavior is unverified** — the candidate does not have access
  to a Windows machine, so none of this could actually be run and tested there.
- **`latest` scans every page** rather than stopping at the first known quote. This is slower
  (about 11 page loads) but always correct, even if quotes appear in the middle or the order changes.
- The site's data is static, so **`latest` will normally find nothing new**. See
  [Demonstrating `latest`](#demonstrating-latest-finding-new-quotes).
- The site accepts any credentials, so a failed login cannot be provoked on it; the check is that the
  "Logout" link appears after submitting the form.
- Ambiguity choices: `page_number` is stored as of the run that first added the row and is never updated
  for existing rows; the "found on the site" count in the summary is the number of quotes scraped
  (before de-duplication); all failures print `Error: ...` and exit with code 1.
- Retries: 3 attempts per navigation, waiting 2 s then 4 s; 15 s timeout per action.

## Install

Requires Python 3.9+. If `pip install -e .` complains about editable mode, upgrade pip first
(`python -m pip install --upgrade pip`); the pip bundled with older Pythons is too old.

### Method A: clone and install editable

```bash
git clone https://github.com/keskarsiddhant-oss/quotes-scraper-siddhant-keskar.git
cd quotes-scraper-siddhant-keskar
python -m venv .venv
```

Activate the virtual environment:

- macOS / Linux: `source .venv/bin/activate`
- Windows (PowerShell): `.venv\Scripts\Activate.ps1`
- Windows (cmd): `.venv\Scripts\activate.bat`

  PowerShell's default execution policy blocks running scripts, so `Activate.ps1` can fail with a
  message like "cannot be loaded because running scripts is disabled on this system". If that
  happens, either use the cmd.exe activation above instead, or allow the script for the current
  session only: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned`.

```bash
python -m pip install --upgrade pip
pip install -e .
playwright install chromium
```

### Method B: install straight from GitHub

```bash
pip install "git+https://github.com/keskarsiddhant-oss/quotes-scraper-siddhant-keskar.git"
playwright install chromium
```

`playwright install chromium` is a one-time step. If you forget it, the tool prints
`Chromium is not installed for Playwright. Run this once...` and exits with code 1.

With method B the default `data/memory.csv` is created relative to the directory you run the command
in; use `--memory-file` to choose another location.

## Supplying login details

```bash
cp .env.example .env        # Windows: copy .env.example .env
```

Edit `.env`:

```
QUOTES_USERNAME=your-username-here
QUOTES_PASSWORD=your-password-here
```

This toy site accepts **any** non-empty username and password. `.env` is git-ignored; never commit it.
The `.env` file is looked up in the directory you run the command from (real environment variables also work).
The password is never printed or logged.

## Usage

```bash
quotes-scraper --help
quotes-scraper backfill --help

quotes-scraper backfill                       # headless (default), data/memory.csv
quotes-scraper backfill --headless            # same, explicit
quotes-scraper backfill --no-headless         # show the browser window
quotes-scraper backfill --memory-file out/quotes.csv

quotes-scraper latest                         # append only quotes not already in memory
quotes-scraper latest --no-headless
quotes-scraper latest --memory-file out/quotes.csv

python -m quotes_scraper latest               # equivalent to the command
```

- `backfill`: scrapes everything and merges into the memory file, then prints how many quotes were
  found, added and skipped as duplicates. Re-running it never creates duplicates.
- `latest`: appends only unseen quotes and leaves existing rows untouched. Prints exactly
  `No new quotes found.` (exit code 0) if there is nothing new, otherwise the number added.
  A missing memory file is treated as empty memory (and reported).

## Output / memory file

- Default path `data/memory.csv` (override with `--memory-file`); the directory and file are created if missing.
- Columns, in order: `quote`, `author`, `tags`, `page_number`.
- `tags` is one string, tags separated by `;` (e.g. `love;life`); `page_number` is an integer.
- UTF-8 encoded (quotes contain curly quotes), standard `csv` module, written with `newline=""`.
  If Excel garbles the characters, use *Data → From Text/CSV* and choose UTF-8.
- Saving writes a temporary file in the same folder and then atomically replaces the target,
  so a crash cannot corrupt existing memory.

## Duplicate detection

A quote's identity key is `(normalized quote text, normalized author)`, where normalizing means
stripping whitespace, collapsing internal whitespace and `casefold()`ing (`storage.identity_key`).

- **`page_number` is not in the key**: if quotes are added upstream, an existing quote moves to another
  page but is still the same quote. Including the page would make it look new.
- Normalizing makes the key robust to harmless differences in whitespace or capitalisation.
- Tags are not in the key, since they can be edited without the quote being a different quote.

## Demonstrating `latest` finding new quotes

1. Run `quotes-scraper backfill`.
2. Open `data/memory.csv` and delete a few data rows (keep the header).
3. Run `quotes-scraper latest`. It re-adds exactly the deleted quotes (at the end of the file) and prints how many.
4. Run it again: `No new quotes found.`

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The tests need no network or browser: `test_storage.py` covers the duplicate key, merging and CSV
round-trip; `test_parsing.py` parses saved HTML pages from `tests/fixtures/`.
