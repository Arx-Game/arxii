"""A refusal is deduplicated on SHA and status, not SHA alone (#4897).

The bot's own fix commit carries a resolved comment naming that SHA; matching the
SHA alone swallowed the refusal that followed it. Runs the real function body,
extracted from the driver, against stubbed comments.
"""

import os
from pathlib import Path
import subprocess

DRIVER = Path(__file__).resolve().parents[2] / "tools/auto_rebase_migration_ci.sh"
SHA = "454a748298576acf0bd11a70677d42c49eed0c1d"


def already_refused(comment: str) -> bool:
    script = f"""
        gh() {{ printf '%s\\n' "$COMMENT"; }}
        MARKER='<!-- migration-auto-rebase'
        eval "$(sed -n '/^already_refused()/,/^}}/p' {DRIVER})"
        already_refused 4866 {SHA}
    """
    proc = subprocess.run(
        ["bash", "-c", script], env={"PATH": os.environ["PATH"], "COMMENT": comment}, check=False
    )
    return proc.returncode == 0


def test_an_earlier_resolved_comment_is_not_a_refusal():
    assert not already_refused(f"<!-- migration-auto-rebase sha={SHA} status=resolved -->")


def test_an_earlier_refusal_is():
    assert already_refused(f"<!-- migration-auto-rebase sha={SHA} status=refused -->")
