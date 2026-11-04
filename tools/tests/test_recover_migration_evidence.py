"""Recovery checks the original report and never publishes a result on a moved PR."""

import subprocess

import pytest
import recover_migration_evidence as recovery

REPOSITORY = "Arx-Game/arxii"
HEAD = "a" * 40
PR = {
    "number": 4985,
    "title": "Feature",
    "state": "OPEN",
    "isCrossRepository": False,
    "baseRefName": "main",
    "headRefOid": HEAD,
    "body": "Closes #4984\n\n## Review evidence\n\n<!-- review-evidence-required -->\n"
    "- Report: https://github.com/Arx-Game/arxii/issues/4984#issuecomment-123\n",
}


def test_paginated_api_handles_multiple_pages_on_older_gh(monkeypatch):
    def run(command, **kwargs):
        assert "--slurp" not in command
        assert command[-2:] == ["--jq", ".[]"]
        return subprocess.CompletedProcess(command, 0, '{"number":1}\n{"number":2}\n', "")

    monkeypatch.setattr(recovery.subprocess, "run", run)
    assert recovery.gh_json("api", "repos/a/b/pulls", "--paginate") == [
        {"number": 1},
        {"number": 2},
    ]


def test_recovery_validates_report_against_original_revision(monkeypatch, tmp_path):
    def gh(*args, **kwargs):
        if args[1].endswith("/labels"):
            return [{"name": "review:evidence-required"}]
        assert args[1].endswith("/issues/comments/123")
        return {"body": "original report text"}

    monkeypatch.setattr(recovery, "gh_json", gh)
    monkeypatch.setattr(recovery, "reviewed_revision", lambda *_args: "original-reviewed-sha")

    def validate(path, revision):
        assert path.read_text() == "original report text"
        assert revision == "original-reviewed-sha"
        return ["stale report"]

    monkeypatch.setattr(recovery, "validate_report", validate)
    assert recovery.validate_evidence(tmp_path, REPOSITORY, PR) == ["stale report"]


def test_report_reference_cannot_fetch_another_repository(monkeypatch, tmp_path):
    monkeypatch.setattr(recovery, "gh_json", lambda *_args: [{"name": "review:evidence-required"}])
    pr = {**PR, "body": PR["body"].replace(REPOSITORY, "attacker/other")}
    assert "this repository" in " ".join(recovery.validate_evidence(tmp_path, REPOSITORY, pr))


@pytest.mark.parametrize("publish", [False, True])
def test_publish_requires_unchanged_pr_and_dry_run_never_writes(monkeypatch, tmp_path, publish):
    calls = []

    def gh(*args, **kwargs):
        calls.append(args)
        assert args[0] == "pr", "must not publish after the PR moved"
        return PR if len(calls) == 1 else {**PR, "headRefOid": "b" * 40}

    monkeypatch.setattr(recovery, "gh_json", gh)
    monkeypatch.setattr(recovery, "git", lambda *_args, **_kwargs: HEAD)
    monkeypatch.setattr(recovery, "is_migration_update", lambda *_args: True)
    monkeypatch.setattr(recovery, "validate_evidence", lambda *_args: [])
    assert recovery.recover(tmp_path, REPOSITORY, 4985, publish=publish) is (not publish)


def test_failed_validation_publishes_failure_on_exact_head(monkeypatch, tmp_path):
    def gh(*args, payload=None):
        if args[0] == "pr":
            return PR
        assert args[1] == f"repos/{REPOSITORY}/check-runs"
        assert payload["head_sha"] == HEAD
        assert payload["name"] == "review-evidence"
        assert payload["conclusion"] == "failure"
        return {"html_url": "https://example.test/check"}

    monkeypatch.setattr(recovery, "gh_json", gh)
    monkeypatch.setattr(recovery, "git", lambda *_args, **_kwargs: HEAD)
    monkeypatch.setattr(recovery, "is_migration_update", lambda *_args: True)
    monkeypatch.setattr(recovery, "validate_evidence", lambda *_args: ["invalid report"])
    assert not recovery.recover(tmp_path, REPOSITORY, 4985, publish=True)


def test_ordinary_heads_are_not_recovered(monkeypatch, tmp_path):
    monkeypatch.setattr(recovery, "gh_json", lambda *_args: PR)
    monkeypatch.setattr(recovery, "git", lambda *_args, **_kwargs: HEAD)
    monkeypatch.setattr(recovery, "is_migration_update", lambda *_args: False)
    assert recovery.recover(tmp_path, REPOSITORY, 4985, publish=True)


def test_api_failure_reports_stderr_without_a_traceback(monkeypatch):
    def run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, stderr="HTTP 403: checks write denied")

    monkeypatch.setattr(recovery.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="HTTP 403: checks write denied"):
        recovery.gh_json("api", "repos/a/b/check-runs", payload={})


def test_one_recovery_error_does_not_abort_later_prs(monkeypatch, tmp_path):
    monkeypatch.setattr(recovery, "git", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(recovery, "gh_json", lambda *_args: [{"number": 1}, {"number": 2}])
    monkeypatch.setattr("sys.argv", ["recover", "--repository", REPOSITORY])
    visited = []

    def recover(repo, repository, number, *, publish):
        visited.append(number)
        if number == 1:
            message = "API unavailable"
            raise RuntimeError(message)
        return True

    monkeypatch.setattr(recovery, "recover", recover)
    assert recovery.main() == 1
    assert visited == [1, 2]
