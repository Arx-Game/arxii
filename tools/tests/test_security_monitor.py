"""Tests for tools/security_monitor.py: alert age, escalation, tracking and privacy.

The GitHub calls are exercised through the real ``GhCli`` command construction with a
fake ``_run`` standing in for ``gh``; notification and dispatch run as real
subprocesses so the contract with the maintainer's private commands is tested too.
"""

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sys
import time

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import security_monitor as sm

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
SENTINEL = "PRIVATE-SENTINEL-lodash-CVE-2099-1234-critical"


def _stamp(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeGh(sm.GhCli):
    """Stands in for the ``gh`` binary: records every call, serves canned JSON."""

    def __init__(self) -> None:
        super().__init__()
        self.open_alerts: list[dict] = []
        self.by_number: dict[int, dict] = {}
        self.issues: list[dict] = []
        self.fail_with: str | None = None
        self.calls: list[list[str]] = []
        self.created = 0

    def add_alert(self, number: int, age_hours: float, state: str = "open", **extra) -> dict:
        raw = {
            "number": number,
            "state": state,
            "created_at": _stamp(age_hours),
            "updated_at": _stamp(age_hours),
            # Fields the monitor must never carry anywhere public. Real runs strip
            # them inside gh --jq; the parser is the second line of defence.
            "security_advisory": {"summary": SENTINEL},
            "dependency": {"package": {"name": SENTINEL}},
            **extra,
        }
        self.by_number[number] = raw
        if state == "open":
            self.open_alerts.append(raw)
        return raw

    @property
    def writes(self) -> list[list[str]]:
        return [c for c in self.calls if "-X" in c]

    def _run(self, args) -> str:
        args = list(args)
        self.calls.append(args)
        if self.fail_with:
            raise sm.MonitorError(self.fail_with)
        path = args[1]
        if "-X" in args:
            return self._write(args)
        if "dependabot/alerts?state=open" in path:
            return "".join(json.dumps(a) + "\n" for a in self.open_alerts)
        if "dependabot/alerts/" in path:
            return json.dumps(self.by_number[int(path.rsplit("/", 1)[1])]) + "\n"
        return "".join(json.dumps(i) + "\n" for i in self.issues)

    def _write(self, args: list[str]) -> str:
        path = args[3]
        if path.endswith("/issues"):
            self.created += 1
            number = 100 + self.created
            body = next(a for a in args if a.startswith("body="))[5:]
            self.issues.append({"number": number, "state": "open", "body": body})
            return f"{number}\n"
        if path.endswith("/comments"):
            return "{}"
        issue = int(path.rsplit("/", 1)[1])
        state = next(a for a in args if a.startswith("state="))[6:]
        for row in self.issues:
            if row["number"] == issue:
                row["state"] = state
        return "{}"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A state directory, private notify and dispatch commands, and a fake gh."""
    notify_script = tmp_path / "notify.py"
    notify_script.write_text("import sys\nopen(sys.argv[1], 'a').write(sys.stdin.read() + '\\n')\n")
    dispatch_script = tmp_path / "dispatch.py"
    dispatch_script.write_text(
        "import os, sys\n"
        "open(sys.argv[1], 'a').write(' '.join(sys.argv[2:]) + ' ' + "
        "os.environ['ARX_SECURITY_ALERT'] + '\\n')\n"
    )
    notified = tmp_path / "notified.log"
    dispatched = tmp_path / "dispatched.log"
    state_dir = tmp_path / "monitor"
    gh = FakeGh()
    monkeypatch.setattr(sm, "GhCli", lambda: gh)
    monkeypatch.setenv(sm.STATE_ENV, str(state_dir))
    monkeypatch.setenv(sm.NOTIFY_ENV, f"{sys.executable} {notify_script} {notified}")
    monkeypatch.setenv(sm.DISPATCH_ENV, f"{sys.executable} {dispatch_script} {dispatched}")

    class Env:
        pass

    e = Env()
    e.gh, e.state_dir, e.notified, e.dispatched = gh, state_dir, notified, dispatched

    def run(*extra: str, at: datetime = NOW) -> int:
        return sm.main(["check", *extra], now=at)

    def notices() -> list[dict]:
        if not notified.exists():
            return []
        return [
            ev for line in notified.read_text().splitlines() for ev in json.loads(line)["events"]
        ]

    def dispatches() -> list[str]:
        deadline = time.time() + 5
        while time.time() < deadline:
            if dispatched.exists() and dispatched.read_text().strip():
                time.sleep(0.2)
                break
            time.sleep(0.05)
        return dispatched.read_text().splitlines() if dispatched.exists() else []

    e.run, e.notices, e.dispatches = run, notices, dispatches
    return e


# --- age and escalation -------------------------------------------------------------


@pytest.mark.parametrize(
    ("hours", "stage"), [(0, 0), (23.9, 0), (24, 1), (47.9, 1), (48, 2), (400, 2)]
)
def test_escalation_stage_follows_age(hours, stage):
    assert sm.target_stage(timedelta(hours=hours)) == stage


def test_age_counts_from_original_detection_not_from_updates():
    alert = sm.parse_alert(
        {"number": 1, "state": "open", "created_at": _stamp(50), "updated_at": _stamp(1)}
    )
    assert sm.alert_age(alert, NOW) == timedelta(hours=50)


def test_escalation_fires_once_per_stage_then_repeats_daily():
    alert = sm.parse_alert(
        {"number": 1, "state": "open", "created_at": _stamp(25), "updated_at": _stamp(25)}
    )
    track, events = sm.reconcile_alert(alert, None, NOW)
    assert [e.kind for e in events] == [sm.Kind.NEW_ALERT, sm.Kind.ESCALATION]
    track.pending_dispatch = None
    _, quiet = sm.reconcile_alert(alert, track, NOW + timedelta(hours=4))
    assert quiet == []
    track2, deadline = sm.reconcile_alert(alert, track, NOW + timedelta(hours=24))
    assert [e.detail for e in deadline] == ["past-deadline"]
    _, repeat_early = sm.reconcile_alert(alert, track2, NOW + timedelta(hours=40))
    assert repeat_early == []
    _, repeat = sm.reconcile_alert(alert, track2, NOW + timedelta(hours=48))
    assert [e.kind for e in repeat] == [sm.Kind.ESCALATION]


# --- the acceptance scenarios -------------------------------------------------------


def test_first_run_with_a_49_hour_alert_creates_one_item_and_reports_overdue(env):
    env.gh.add_alert(7, 49)

    assert env.run() == sm.EXIT_OK

    assert env.gh.created == 1
    kinds = [(e["kind"], e.get("detail")) for e in env.notices()]
    assert ("escalation", "past-deadline") in kinds
    assert ("new_alert", None) in kinds
    assert env.dispatches() == ["7 new 7"]


def test_a_run_with_nothing_to_do_starts_no_agent_and_sends_nothing(env):
    env.gh.add_alert(7, 3)
    env.run()
    env.dispatches()
    first_notices, first_writes = len(env.notices()), len(env.gh.writes)

    assert env.run(at=NOW + timedelta(hours=1)) == sm.EXIT_OK

    assert len(env.notices()) == first_notices
    assert len(env.gh.writes) == first_writes
    assert env.dispatches() == ["7 new 7"]


def test_a_second_run_cannot_create_a_second_item_while_one_holds_the_lock(env):
    env.state_dir.mkdir(parents=True)
    holder = sm.RunLock(env.state_dir, NOW)
    assert holder.acquire()
    assert not sm.RunLock(env.state_dir, NOW).acquire()
    env.gh.add_alert(7, 3)

    assert env.run() == sm.EXIT_OK

    assert env.gh.created == 0
    holder.release()


def test_lost_state_finds_the_existing_item_by_marker_instead_of_duplicating(env):
    env.gh.add_alert(7, 3)
    env.run()
    (env.state_dir / "state.json").unlink()

    env.run(at=NOW + timedelta(hours=4))

    assert env.gh.created == 1


def test_a_crashed_holders_lock_expires_and_a_later_run_resumes(env):
    env.state_dir.mkdir(parents=True)
    crashed = sm.RunLock(env.state_dir, NOW - timedelta(hours=2))
    assert crashed.acquire()
    env.gh.add_alert(7, 3)

    assert env.run() == sm.EXIT_OK

    assert env.gh.created == 1
    assert not (env.state_dir / "monitor.lock").exists()


@pytest.mark.parametrize("failure", ["HTTP 403: Resource not accessible", "gh not found"])
def test_a_failed_read_reports_privately_and_never_closes_or_creates(env, failure):
    env.gh.add_alert(7, 3)
    env.run()
    env.dispatches()
    env.gh.fail_with = failure
    env.gh.calls.clear()

    assert env.run(at=NOW + timedelta(hours=4)) == sm.EXIT_FAILED

    assert env.gh.writes == []
    assert [e["kind"] for e in env.notices()][-1] == "failure"
    # A second failure inside a day is not announced again.
    count = len(env.notices())
    env.run(at=NOW + timedelta(hours=8))
    assert len(env.notices()) == count


def test_an_empty_api_answer_is_not_trusted_when_the_call_failed(env):
    env.gh.fail_with = "HTTP 500"
    assert env.run() == sm.EXIT_FAILED
    assert env.gh.created == 0


def test_a_merged_pr_with_the_alert_still_open_keeps_the_item_open(env):
    env.gh.add_alert(7, 30)
    env.run()
    env.gh.calls.clear()

    env.run(at=NOW + timedelta(hours=4))

    assert env.gh.writes == []
    assert env.gh.issues[0]["state"] == "open"


def test_an_agent_with_no_patch_acks_containment_and_the_timer_keeps_running(env):
    env.gh.add_alert(7, 30)
    env.run()
    env.dispatches()
    assert sm.main(["ack", "7", "--outcome", "containment"], now=NOW) == sm.EXIT_OK

    env.run(at=NOW + timedelta(hours=20))

    state = sm.load_state(env.state_dir)
    assert state.tracks[7].outcome == "containment"
    assert state.tracks[7].escalation_stage == 2
    assert env.gh.issues[0]["state"] == "open"
    assert "escalation" in [e["kind"] for e in env.notices()]


def test_the_item_closes_only_when_a_fresh_read_says_fixed(env):
    env.gh.add_alert(7, 30)
    env.run()
    env.gh.open_alerts.clear()
    env.gh.by_number[7]["state"] = "dismissed"

    env.run(at=NOW + timedelta(hours=4))
    assert env.gh.issues[0]["state"] == "open"

    env.gh.by_number[7]["state"] = "fixed"
    env.run(at=NOW + timedelta(hours=8))
    assert env.gh.issues[0]["state"] == "closed"
    assert "fixed" in [e["kind"] for e in env.notices()]


def test_a_reopened_alert_reopens_the_item_and_keeps_its_original_age(env):
    env.gh.add_alert(7, 60)
    env.run()
    env.gh.open_alerts.clear()
    env.gh.by_number[7]["state"] = "fixed"
    env.run(at=NOW + timedelta(hours=4))
    env.gh.by_number[7]["state"] = "open"
    env.gh.open_alerts.append(env.gh.by_number[7])

    env.run(at=NOW + timedelta(hours=8))

    assert env.gh.issues[0]["state"] == "open"
    events = env.notices()
    assert [e["kind"] for e in events][-2:] == ["reopened", "escalation"]
    assert events[-1]["age_hours"] == 68


def test_an_exception_stops_work_but_is_restated_and_keeps_the_timer(env):
    env.gh.add_alert(7, 30)
    env.run()
    env.dispatches()
    assert sm.main(["exception", "7", "--by", "someone"], now=NOW) == sm.EXIT_OK

    env.run(at=NOW + timedelta(hours=4))
    assert env.gh.issues[0]["state"] == "closed"
    assert len(env.dispatches()) == 1

    env.run(at=NOW + timedelta(days=8))
    assert env.notices()[-1]["kind"] == "exception_reminder"
    assert sm.load_state(env.state_dir).tracks[7].exception_at is not None


def test_dispatch_is_bounded_per_run_and_the_rest_waits_for_the_next_run(env):
    for number in (1, 2, 3, 4, 5):
        env.gh.add_alert(number, 3)

    env.run("--max-dispatch", "2")
    assert len(env.dispatches()) == 2

    env.run("--max-dispatch", "2", at=NOW + timedelta(hours=4))
    time.sleep(0.5)
    assert len(env.dispatches()) == 4


def test_a_live_worker_lease_blocks_a_second_dispatch_until_it_ends_or_is_acked(env):
    env.gh.add_alert(7, 30)
    env.run()
    env.dispatches()
    env.gh.by_number[7]["updated_at"] = _stamp(0)
    env.gh.open_alerts[0]["updated_at"] = _stamp(0)

    env.run(at=NOW + timedelta(hours=1))
    assert len(env.dispatches()) == 1

    env.run(at=NOW + timedelta(hours=7))
    time.sleep(0.5)
    assert len(env.dispatches()) == 2


def test_a_retry_is_dispatched_at_most_once_a_day(env):
    env.gh.add_alert(7, 3)
    env.run()
    env.dispatches()

    env.run(at=NOW + timedelta(hours=12))
    assert len(env.dispatches()) == 1
    env.run(at=NOW + timedelta(hours=25))
    time.sleep(0.5)
    assert len(env.dispatches()) == 2


def test_a_failed_notification_commits_nothing_and_the_next_run_retries_it(env, monkeypatch):
    env.gh.add_alert(7, 49)
    monkeypatch.setenv(sm.NOTIFY_ENV, f"{sys.executable} -c 'import sys; sys.exit(1)'")

    assert env.run() == sm.EXIT_FAILED
    assert (
        not (env.state_dir / "state.json").exists() or 7 not in sm.load_state(env.state_dir).tracks
    )
    assert env.dispatches() == []
    assert env.gh.created == 1

    monkeypatch.setenv(sm.NOTIFY_ENV, f"{sys.executable} -c 'import sys; sys.stdin.read()'")
    assert env.run(at=NOW + timedelta(hours=4)) == sm.EXIT_OK
    assert env.gh.created == 1
    assert env.dispatches() == ["7 new 7"]


def test_the_first_run_after_downtime_reports_the_gap(env):
    env.gh.add_alert(7, 3)
    env.run()

    env.run(at=NOW + timedelta(hours=30))

    assert "missed_runs" in [e["kind"] for e in env.notices()]


def test_status_fails_when_no_recent_successful_check_exists(env):
    assert sm.main(["status"], now=NOW) == sm.EXIT_STALE
    env.gh.add_alert(7, 3)
    env.run()
    assert sm.main(["status"], now=NOW + timedelta(hours=1)) == sm.EXIT_OK
    assert sm.main(["status"], now=NOW + timedelta(hours=12)) == sm.EXIT_STALE


# --- privacy and configuration ------------------------------------------------------


def test_no_private_alert_text_reaches_any_public_or_stored_surface(env):
    env.gh.add_alert(7, 49)
    env.gh.add_alert(8, 3)
    env.run()
    env.gh.by_number[7]["state"] = "fixed"
    env.gh.open_alerts[:] = [a for a in env.gh.open_alerts if a["number"] != 7]
    env.run(at=NOW + timedelta(hours=4))

    public = json.dumps([env.gh.writes, env.gh.issues])
    private_but_stored = (env.state_dir / "state.json").read_text()
    sent = env.notified.read_text() + "".join(env.dispatches())
    for surface in (public, private_but_stored, sent):
        assert SENTINEL not in surface
        assert "lodash" not in surface
    assert "alerts?" not in json.dumps(env.gh.issues)


def test_the_tracking_body_is_a_marker_and_a_protected_link_only():
    body = sm.tracking_body(7)
    assert sm.MARKER_RE.search(body).group(1) == "7"
    assert "security/dependabot/7" in body


def test_dry_run_changes_nothing_and_needs_no_private_commands(env, monkeypatch, capsys):
    env.gh.add_alert(7, 49)
    monkeypatch.delenv(sm.NOTIFY_ENV)
    monkeypatch.delenv(sm.DISPATCH_ENV)

    assert env.run("--dry-run") == sm.EXIT_OK

    out = capsys.readouterr().out
    assert "alert 7: state open, age 49h" in out
    assert "dispatch (new)" in out
    assert env.gh.writes == []
    assert not env.state_dir.exists()


def test_a_real_run_without_private_commands_fails_clearly(env, monkeypatch):
    monkeypatch.delenv(sm.NOTIFY_ENV)
    assert env.run() == sm.EXIT_FAILED
    assert env.gh.calls == []


def test_the_state_directory_must_be_outside_the_checkout(env, monkeypatch):
    monkeypatch.setenv(sm.STATE_ENV, str(sm.CHECKOUT_ROOT / "tools" / "state"))
    assert env.run("--dry-run") == sm.EXIT_FAILED


def test_an_alert_response_without_a_creation_time_is_an_error_not_an_alert():
    with pytest.raises(sm.MonitorError):
        sm.parse_alert({"number": 1, "state": "open"})
