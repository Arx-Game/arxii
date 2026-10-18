"""prod_migration_check.sh reports the migration production last APPLIED, not the
highest name (#4422).

The helper's tip query is pulled out of the script and run on a sqlite table
shaped like django_migrations. The dump that exposed the bug holds rows from an
older squashed generation whose names sort above the real tip.
"""

from __future__ import annotations

from pathlib import Path
import re
import sqlite3

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "prod_migration_check.sh"


def _tip_sql() -> str:
    match = re.search(r'^applied_tip\(\) \{ q "(.+)"; \}$', SCRIPT.read_text(), re.MULTILINE)
    assert match, "applied_tip() query not found in prod_migration_check.sh"
    return match.group(1).replace("${APP_LABEL}", "arxii")


@pytest.fixture
def dump_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "create table django_migrations (id integer primary key, app text, name text, applied text)"
    )
    rows = [
        # Old generation: higher names, applied months earlier.
        (357, "arxii", "0228_codex_entry_filing", "2026-09-06 05:51:42"),
        (358, "arxii", "0227_family_templates_contract", "2026-09-05 17:39:36"),
        # Current generation: the real last apply.
        (592, "arxii", "0221_carry_desc_attribute_text", "2026-10-14 16:35:00"),
        (593, "arxii", "0222_drop_sheet_marital_status", "2026-10-14 16:35:01"),
        (594, "other_app", "0999_not_ours", "2026-10-15 00:00:00"),
    ]
    conn.executemany("insert into django_migrations values (?, ?, ?, ?)", rows)
    return conn


def test_tip_is_latest_applied_not_highest_name(dump_db: sqlite3.Connection):
    (tip,) = dump_db.execute(_tip_sql()).fetchone()
    assert tip == "0222_drop_sheet_marital_status"


def test_tip_breaks_same_timestamp_ties_by_id(dump_db: sqlite3.Connection):
    dump_db.execute(
        "insert into django_migrations values "
        "(595, 'arxii', '0223_same_second', '2026-10-14 16:35:01')"
    )
    (tip,) = dump_db.execute(_tip_sql()).fetchone()
    assert tip == "0223_same_second"
