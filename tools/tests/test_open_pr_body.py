"""open-pr.sh must emit a PR body the review-evidence check accepts.

The ``- Report:`` line was wrapped, double-wrapped and unwrapped across #3785,
#3786, #3794 and #3798 because nothing fed the script's own output to the
validator; the only end-to-end check was a later PR's first CI run (#3802).
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from validate_review_evidence import REPORT_LINE, validate_pr_body

ROOT = Path(__file__).resolve().parents[2]
OPEN_PR = ROOT / "tools/skills/issue-to-merged-pr/scripts/open-pr.sh"
ISSUE = "1234"

# Stand-ins for the external commands open-pr.sh calls before its dry-run exit,
# so the body is built exactly as a real run builds it, with no network.
_GH_STUB = """#!/usr/bin/env bash
case "$*" in
  *"issue view"*labels*) echo "review:evidence-required" ;;
  *"issue view"*title*) echo "Stub issue title" ;;
  *"issue view"*assignees*) echo "stub-user" ;;
  "api user"*) echo "stub-user" ;;
  "repo view"*) echo "Arx-Game/arxii" ;;
  "api repos/"*) echo "stub report" ;;
  *) echo "unexpected gh call: $*" >&2; exit 1 ;;
esac
"""
_STUBS = {
    "gh": _GH_STUB,
    "git": '#!/usr/bin/env bash\necho "' + "a" * 40 + '"\n',
    "uv": "#!/usr/bin/env bash\nexit 0\n",
}


def _dry_run_body(evidence_env: dict[str, str]) -> str:
    with tempfile.TemporaryDirectory() as directory:
        for name, script in _STUBS.items():
            stub = Path(directory) / name
            stub.write_text(script, encoding="utf-8")
            stub.chmod(0o755)
        env = {key: value for key, value in os.environ.items() if not key.startswith("PR_")}
        env.update(evidence_env)
        env["PATH"] = f"{directory}{os.pathsep}{env['PATH']}"
        result = subprocess.run(
            ["bash", str(OPEN_PR), "--dry-run", "some-branch", ISSUE],
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT,
            check=False,
        )
    if result.returncode != 0:
        message = f"open-pr.sh --dry-run failed:\n{result.stderr}"
        raise AssertionError(message)
    _, _, body = result.stdout.partition("  body:\n")
    return "\n".join(line.removeprefix("    ") for line in body.splitlines())


class OpenPrBodyTests(unittest.TestCase):
    def assert_report_line(self, body: str, expected: str) -> None:
        self.assertEqual(validate_pr_body(body, expected_issue=ISSUE), [])
        report_lines = [line for line in body.splitlines() if line.startswith("- Report:")]
        self.assertEqual(report_lines, [expected])
        self.assertIsNotNone(REPORT_LINE.search(body))

    def test_committed_report_path_is_backtick_wrapped_once(self) -> None:
        body = _dry_run_body({"PR_EVIDENCE_FILE": "docs/reviews/1234.md"})
        self.assert_report_line(body, "- Report: `docs/reviews/1234.md`")

    def test_comment_url_is_left_bare(self) -> None:
        url = "https://github.com/Arx-Game/arxii/issues/1234#issuecomment-1"
        body = _dry_run_body({"PR_EVIDENCE_URL": url})
        self.assert_report_line(body, f"- Report: {url}")


if __name__ == "__main__":
    unittest.main()
