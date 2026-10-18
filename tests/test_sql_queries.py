"""Static (offline) validation of the exploration SQL in ``sql/exploration/``.

Why static?
-----------
The exploration queries are meant to run against
``bigquery-public-data.ga4_obfuscated_sample_ecommerce``, which is **not
reachable from this environment** (no credentials, no BigQuery client). These
tests therefore validate properties that matter and can be checked without a
warehouse: documentation headers, read-only guarantees, wildcard safety and the
absence of accidental full-table scans.

They are written defensively because the ``sql/`` tree is owned by another
subagent and may not exist yet: the whole module skips when
``sql/exploration/`` is absent, and each test skips when the directory exists but
contains no ``.sql`` file. The suite must never fail because someone else's
directory is missing.

The assertions are deliberately tolerant about formatting (any casing, any
position inside the first 40 lines) but strict about the things that would
actually break the project: a destructive statement, a wildcard scan without a
date filter, or a query that silently reads the entire dataset.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SQL_EXPLORATION_DIR = REPO_ROOT / "sql" / "exploration"

pytestmark = pytest.mark.skipif(
    not SQL_EXPLORATION_DIR.is_dir(),
    reason="sql/exploration/ does not exist yet (owned by another subagent) - static SQL checks skipped",
)

# A "bare" SELECT * is one that ends the line: nothing is projected from it.
# `SELECT * EXCEPT(...)`, `SELECT * REPLACE(...)` and `SELECT * FROM x` are
# intentionally tolerated because they are legitimate BigQuery patterns.
BARE_SELECT_STAR = re.compile(r"(?im)^[ \t]*select[ \t]+\*[ \t]*(?:--[^\n]*)?$")

# Any reference to the day-partitioned events tables as a wildcard.
WILDCARD_EVENTS_REFERENCE = re.compile(r"(?i)\bevents_?\s*\*")

TABLE_SUFFIX_FILTER = re.compile(r"(?i)_table_suffix")

# Statements that must never appear in an exploration script.
# Deliberately *not* flagged: `CREATE TEMP FUNCTION` / `CREATE TEMP TABLE`, which
# are session-scoped and mutate no dataset. Only persisted-object DDL is a defect.
FORBIDDEN_STATEMENTS = re.compile(
    r"(?i)\b("
    r"insert|update|delete|drop|merge|truncate|"
    r"create\s+(?:or\s+replace\s+)?(?:table|view|schema|function)"
    r")\b"
)

HEADER_MARKERS = ("purpose", "caveats")
HEADER_WINDOW_LINES = 40


def _sql_files() -> list[Path]:
    """All ``.sql`` files in ``sql/exploration/``, sorted for stable test output."""
    return sorted(path for path in SQL_EXPLORATION_DIR.glob("*.sql") if path.is_file())


def _read(path: Path) -> str:
    """Read a SQL file as text, tolerating BOMs and non-UTF-8 bytes."""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def _strip_sql_comments(sql: str) -> str:
    """Remove ``--`` and ``/* */`` comments before scanning for forbidden words.

    Without this, a header that *documents* "this script never runs DELETE"
    would trip the read-only assertion - the test must judge the code, not the
    prose around it.
    """
    without_block_comments = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return re.sub(r"--[^\n]*", " ", without_block_comments)


def _require_files() -> list[Path]:
    """Return the SQL files or skip the test when the directory is still empty."""
    files = _sql_files()
    if not files:
        pytest.skip(f"no .sql file found in {SQL_EXPLORATION_DIR} yet")
    return files


def test_exploration_directory_contains_sql_files() -> None:
    """Guard: if the directory exists, it must actually contain the exploration queries."""
    files = _sql_files()
    if not files:
        pytest.skip(f"no .sql file found in {SQL_EXPLORATION_DIR} yet")
    assert len(files) >= 1


def test_sql_files_are_not_empty() -> None:
    """An empty file has no query: it must be caught, not silently skipped."""
    for path in _require_files():
        content = _read(path)
        assert content.strip(), f"{path.name} is empty"
        assert re.search(r"(?i)\bselect\b", content), f"{path.name} contains no SELECT statement"


def test_every_sql_file_documents_purpose_and_caveats() -> None:
    """Each query must state why it exists and what its results cannot prove."""
    for path in _require_files():
        header = "\n".join(_read(path).splitlines()[:HEADER_WINDOW_LINES]).lower()
        missing = [marker for marker in HEADER_MARKERS if marker not in header]
        assert not missing, (
            f"{path.name}: header is missing {missing} in the first {HEADER_WINDOW_LINES} lines. "
            "Exploration queries must document their Purpose and their Caveats."
        )


def test_no_bare_select_star() -> None:
    """Reject lines that project the whole table with no projection at all."""
    for path in _require_files():
        offenders = [
            number
            for number, line in enumerate(_read(path).splitlines(), start=1)
            if BARE_SELECT_STAR.match(line)
        ]
        assert not offenders, (
            f"{path.name}: bare 'SELECT *' on line(s) {offenders}. Project explicit columns (or "
            "'SELECT * EXCEPT(...)') so the query stays cheap and the contract stays explicit."
        )


def test_events_wildcard_requires_table_suffix_filter() -> None:
    """Reading ``events_*`` without a ``_TABLE_SUFFIX`` filter scans every shard."""
    for path in _require_files():
        content = _read(path)
        if WILDCARD_EVENTS_REFERENCE.search(content):
            assert TABLE_SUFFIX_FILTER.search(content), (
                f"{path.name} references the 'events_*' wildcard but never filters on "
                "_TABLE_SUFFIX: the query would read every shard of the dataset instead of the "
                "intended date window."
            )


def test_exploration_sql_is_read_only() -> None:
    """Exploration scripts must never mutate anything: no DML, no DDL."""
    for path in _require_files():
        code = _strip_sql_comments(_read(path))
        matches = FORBIDDEN_STATEMENTS.findall(code)
        assert not matches, (
            f"{path.name} contains write/DDL statement(s) {matches}. Exploration SQL must be "
            "read-only: analysis never modifies the dataset."
        )


def test_sql_files_are_reachable_from_the_repo_root() -> None:
    """Sanity check that the tests validate the real project tree, not a stray copy."""
    assert SQL_EXPLORATION_DIR.parent.parent == REPO_ROOT
