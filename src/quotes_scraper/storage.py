"""CSV memory: loading, duplicate detection, merging and safe saving."""

import csv
import os
import tempfile
from pathlib import Path

# Column order of the CSV. Every record has exactly these fields.
FIELDS = ["quote", "author", "tags", "page_number"]


class StorageError(Exception):
    """Raised when the memory file cannot be read or is not in our format."""


def _normalize(text):
    """Strip, collapse internal whitespace and casefold."""
    return " ".join(text.split()).casefold()


def identity_key(quote, author):
    """Return the duplicate-detection key for a record.

    The key is the normalized quote text plus the normalized author.
    page_number is deliberately NOT part of it: if quotes are added upstream
    the same quote moves to another page, but it is still the same quote.
    """
    return (_normalize(quote), _normalize(author))


def load_memory(path):
    """Return the rows stored at `path` as a list of dicts.

    A missing file is treated as empty memory (returns []).
    """
    path = Path(path)
    if not path.exists():
        return []
    try:
        # utf-8-sig also accepts a BOM, which Excel adds when saving as CSV UTF-8.
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:  # completely empty file
                return []
            if reader.fieldnames != FIELDS:
                raise StorageError(
                    f"{path} has columns {reader.fieldnames}, expected {FIELDS}. "
                    "Fix or remove the file, or choose another --memory-file."
                )
            return list(reader)
    except (OSError, UnicodeDecodeError) as exc:
        raise StorageError(f"Could not read {path}: {exc}") from exc


def merge(existing, scraped):
    """Append records from `scraped` whose key is not yet known.

    Existing rows are kept untouched and in order. Duplicates inside `scraped`
    itself are also skipped. Returns (merged_rows, added_count, skipped_count).
    """
    seen = {identity_key(r["quote"], r["author"]) for r in existing}
    merged = list(existing)
    added = 0
    for row in scraped:
        key = identity_key(row["quote"], row["author"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
        added += 1
    return merged, added, len(scraped) - added


def save_memory(path, rows):
    """Write `rows` to `path` atomically.

    We write a temporary file in the same directory and then os.replace() it
    over the target, so a crash mid-write never leaves a half-written memory file.
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Same directory => same filesystem, which os.replace needs to be atomic.
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            os.replace(tmp_name, path)  # atomic and cross-platform, unlike os.rename on Windows
        except BaseException:
            tmp_path = Path(tmp_name)
            if tmp_path.exists():
                tmp_path.unlink()
            raise
    except OSError as exc:
        raise StorageError(f"Could not write {path}: {exc}") from exc
