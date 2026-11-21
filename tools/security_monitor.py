#!/usr/bin/env python3
"""Reconcile Dependabot security alerts with generic public tracking issues.

Run by an operating-system scheduler on the maintainer's own machine (every 4 hours),
inside the authenticated development container. The check is deterministic and never
calls a language model: it starts an agent only when a decision below says there is
work (see ``docs/operations/security-alert-triage.md`` for the contract).

**This repo is public, so nothing about an alert ever leaves the protected API.** The
GitHub calls filter each alert down to its number, state and timestamps before this
process sees it, and every public write (a tracking issue's title, body and comments)
is built from the alert number alone. Package names, severities, advisory text and
versions are never read, stored, logged or notified. Anything you add must pass that
test; ``tools/tests/test_security_monitor.py`` injects sentinel text to check it.

Local bookkeeping lives in a state directory outside the checkout and holds alert
numbers, states and timestamps only.
"""

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, fields, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time
import uuid

from sentry_constants import GH_REPO

TRACKING_LABEL = "security-alert"
TRACKING_TITLE = "Security alert follow-up (alert {number})"
MARKER_TEMPLATE = "<!-- security-alert-tracking:alert={number} -->"
MARKER_RE = re.compile(r"<!-- security-alert-tracking:alert=(\d{1,9}) -->", re.ASCII)
ALERT_URL = f"https://github.com/{GH_REPO}/security/dependabot/{{number}}"

CHECK_INTERVAL = timedelta(hours=4)
MISSED_RUN_AFTER = CHECK_INTERVAL * 2 + timedelta(hours=1)
DEADLINE_STAGE = 2
FIRST_ESCALATION = timedelta(hours=24)
DEADLINE = timedelta(hours=48)
REPEAT_ESCALATION = timedelta(hours=24)
RETRY_INTERVAL = timedelta(hours=24)
EXCEPTION_REMINDER = timedelta(days=7)
FAILURE_NOTICE_INTERVAL = timedelta(hours=24)
WORKER_LEASE = timedelta(hours=6)
LOCK_TTL = timedelta(hours=2)
LOCK_WAIT_SECONDS = 120
DISPATCH_GRACE_SECONDS = 3
DEFAULT_MAX_DISPATCH = 3
SUBPROCESS_TIMEOUT = 120

DISPATCH_REASONS = frozenset({None, "new", "reopened", "changed", "escalation", "retry"})
STATE_ENV = "ARX_SECURITY_MONITOR_DIR"
NOTIFY_ENV = "ARX_SECURITY_NOTIFY_CMD"
DISPATCH_ENV = "ARX_SECURITY_DISPATCH_CMD"
BRIEF_PATH = Path(__file__).with_name("security_alert_agent_brief.md")
CHECKOUT_ROOT = Path(__file__).resolve().parent.parent

# The only alert fields that ever reach this process (applied inside ``gh --jq``).
ALERT_JQ = "{number, state, created_at, updated_at}"
ISSUE_JQ = '.[] | select(has("pull_request") | not) | {number, state, body}'

EXIT_OK = 0
EXIT_ERRORS = 1
EXIT_FAILED = 2
EXIT_STALE = 3


class MonitorError(RuntimeError):
    """A required capability failed; the run reports it and changes nothing public."""


class Kind(StrEnum):
    NEW_ALERT = "new_alert"
    REOPENED = "reopened"
    CHANGED = "changed"
    ESCALATION = "escalation"
    FIXED = "fixed"
    EXCEPTION_REMINDER = "exception_reminder"
    MISSED_RUNS = "missed_runs"
    FAILURE = "failure"
    AGENT_UNACKNOWLEDGED = "agent_unacknowledged"
    AGENT_OUTCOME = "agent_outcome"
    STATE_REBUILT = "state_rebuilt"
    PROBE = "probe"


class Outcome(StrEnum):
    FIX_PROPOSED = "fix-proposed"
    CONTAINMENT = "containment"
    BLOCKED = "blocked"
    NO_ACTION = "no-action"


@dataclass(frozen=True)
class Alert:
    """An alert reduced to what the monitor needs; no advisory content."""

    number: int
    state: str
    created_at: datetime
    updated_at: datetime | None

    @property
    def unresolved(self) -> bool:
        """Only a fresh read showing ``fixed`` resolves an alert; dismissal does not."""
        return self.state != "fixed"


@dataclass(frozen=True)
class Event:
    """One thing to tell the maintainer privately. Numbers and fixed words only."""

    kind: Kind
    alert: int | None = None
    age_hours: int | None = None
    detail: str = ""

    def as_json(self) -> dict:
        data: dict = {"kind": str(self.kind)}
        if self.alert is not None:
            data["alert"] = self.alert
            data["protected_url"] = ALERT_URL.format(number=self.alert)
        if self.age_hours is not None:
            data["age_hours"] = self.age_hours
        if self.detail:
            data["detail"] = self.detail
        return data


@dataclass
class Track:
    """Local bookkeeping for one alert. Never holds advisory text or credentials."""

    last_state: str = "open"
    last_updated_at: datetime | None = None
    escalation_stage: int = 0
    last_escalated_at: datetime | None = None
    last_reminder_at: datetime | None = None
    last_dispatch_at: datetime | None = None
    lease_expires_at: datetime | None = None
    pending_dispatch: str | None = None
    outcome: str | None = None
    outcome_reported_at: datetime | None = None
    detected_at: datetime | None = None
    exception_at: datetime | None = None
    exception_by: str | None = None
    issue: int | None = None
    wanted_issue_state: str = "open"


@dataclass
class State:
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_notice_at: datetime | None = None
    tracks: dict[int, Track] = field(default_factory=dict)


@dataclass(frozen=True)
class TrackingIssue:
    number: int
    state: str


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).astimezone(UTC) if value else None


def parse_alert(raw: dict) -> Alert:
    """Build an Alert from a raw API object, taking only the whitelisted fields."""
    created = _parse_time(raw.get("created_at"))
    if created is None or not isinstance(raw.get("number"), int):
        msg = "alert response is missing its number or creation time"
        raise MonitorError(msg)
    return Alert(
        number=raw["number"],
        state=str(raw.get("state") or "open"),
        created_at=created,
        updated_at=_parse_time(raw.get("updated_at")),
    )


# --- Pure decisions -----------------------------------------------------------------


def alert_age(alert: Alert, now: datetime) -> timedelta:
    """Age counts from original detection, never from a PR, a retry or a reopening."""
    return now - alert.created_at


def _age_hours(age: timedelta) -> int:
    return int(age.total_seconds() // 3600)


def target_stage(age: timedelta) -> int:
    """Escalation stage an alert of this age has reached: 0, 1 (24h) or 2 (deadline)."""
    if age >= DEADLINE:
        return 2
    return 1 if age >= FIRST_ESCALATION else 0


def _escalate(track: Track, age: timedelta, now: datetime, events: list[Event]) -> None:
    """Fire the escalation now due. An alert first seen past the deadline fires once."""
    stage = target_stage(age)
    repeat_due = (
        stage == DEADLINE_STAGE
        and track.escalation_stage == DEADLINE_STAGE
        and track.last_escalated_at is not None
        and now - track.last_escalated_at >= REPEAT_ESCALATION
    )
    if stage > track.escalation_stage or repeat_due:
        track.escalation_stage = stage
        track.last_escalated_at = now
        track.pending_dispatch = track.pending_dispatch or "escalation"
        detail = "past-deadline" if stage == DEADLINE_STAGE else "approaching-deadline"
        events.append(Event(Kind.ESCALATION, age_hours=_age_hours(age), detail=detail))


def _retry_due(track: Track, now: datetime) -> bool:
    return (
        track.last_dispatch_at is not None
        and not _lease_live(track, now)
        and now - track.last_dispatch_at >= RETRY_INTERVAL
    )


def _lease_live(track: Track, now: datetime) -> bool:
    return track.lease_expires_at is not None and track.lease_expires_at > now


def _watch_worker(track: Track, now: datetime, events: list[Event]) -> None:
    """Say so when an agent run ends without an ack, or ends blocked or containing."""
    lapsed = track.lease_expires_at is not None and track.lease_expires_at <= now
    if lapsed and track.outcome is None:
        # Free the lease and tell the maintainer. The daily retry, not an immediate
        # redispatch, follows: an agent that works but forgets to ack must not cost a run
        # every 6 hours.
        track.lease_expires_at = None
        events.append(Event(Kind.AGENT_UNACKNOWLEDGED))
    reportable = track.outcome in (Outcome.BLOCKED, Outcome.CONTAINMENT)
    if reportable and track.outcome_reported_at is None:
        track.outcome_reported_at = now
        events.append(Event(Kind.AGENT_OUTCOME, detail=str(track.outcome)))


def _reopen(track: Track) -> None:
    """A fixed alert is open again: the escalation clock restarts against its original age."""
    track.escalation_stage = 0
    track.last_escalated_at = None
    track.last_dispatch_at = None
    track.lease_expires_at = None
    track.outcome = None
    track.outcome_reported_at = None
    track.exception_at = None
    track.exception_by = None
    track.pending_dispatch = "reopened"


def reconcile_alert(
    alert: Alert, previous: Track | None, now: datetime
) -> tuple[Track | None, list[Event]]:
    """Decide what one alert needs. Pure: the same inputs always give the same answer."""
    events: list[Event] = []
    age = alert_age(alert, now)
    hours = _age_hours(age)
    if previous is None:
        if not alert.unresolved:
            return None, events
        track = Track(pending_dispatch="new")
        events.append(Event(Kind.NEW_ALERT, alert.number, hours))
    else:
        track = replace(previous)
        _observe_existing(alert, track, events)
    track.last_state = alert.state
    track.last_updated_at = alert.updated_at
    track.detected_at = alert.created_at
    if alert.unresolved and track.exception_at is None:
        _watch_worker(track, now, events)
        _escalate(track, age, now, events)
        if _retry_due(track, now):
            track.pending_dispatch = track.pending_dispatch or "retry"
    elif alert.unresolved:
        _remind_exception(track, age, now, events)
    track.wanted_issue_state = "open" if _needs_open_issue(alert, track) else "closed"
    events[:] = [replace(e, alert=alert.number, age_hours=hours) for e in events]
    return track, events


def _needs_open_issue(alert: Alert, track: Track) -> bool:
    return alert.unresolved and track.exception_at is None


def _observe_existing(alert: Alert, track: Track, events: list[Event]) -> None:
    was_fixed = track.last_state == "fixed"
    if was_fixed and alert.unresolved:
        _reopen(track)
        events.append(Event(Kind.REOPENED))
    elif not alert.unresolved and not was_fixed:
        track.pending_dispatch = None
        events.append(Event(Kind.FIXED))
    elif (
        alert.unresolved
        and track.exception_at is None
        and alert.updated_at != track.last_updated_at
    ):
        track.pending_dispatch = track.pending_dispatch or "changed"
        events.append(Event(Kind.CHANGED))


def _remind_exception(track: Track, age: timedelta, now: datetime, events: list[Event]) -> None:
    """An exception never silences an unresolved alert: it is restated weekly."""
    last = track.last_reminder_at or track.exception_at
    if last is not None and now - last >= EXCEPTION_REMINDER:
        track.last_reminder_at = now
        events.append(Event(Kind.EXCEPTION_REMINDER, age_hours=_age_hours(age)))


def missed_run_events(state: State, now: datetime) -> list[Event]:
    """Report a gap since the last good check (an offline host cannot warn about itself)."""
    last = state.last_success_at
    if last is None or now - last <= MISSED_RUN_AFTER:
        return []
    return [Event(Kind.MISSED_RUNS, age_hours=_age_hours(now - last))]


# --- GitHub access ------------------------------------------------------------------


class GhCli:
    """The GitHub calls the monitor makes, through the container's authenticated ``gh``.

    Credentials stay inside ``gh``; none of them is read, passed or printed here. Tests
    subclass this and override the public methods.
    """

    def __init__(self, repo: str = GH_REPO) -> None:
        self.repo = repo

    def _run(self, args: Sequence[str]) -> str:
        try:
            result = subprocess.run(  # noqa: S603
                ["gh", *args],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
                timeout=SUBPROCESS_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            msg = f"gh could not run ({type(exc).__name__})"
            raise MonitorError(msg) from None
        if result.returncode != 0:
            first_line = (result.stderr.strip().splitlines() or ["no error text"])[0]
            msg = f"gh api failed: {first_line[:200]}"
            raise MonitorError(msg)
        return result.stdout

    def _objects(self, args: Sequence[str]) -> list[dict]:
        out = self._run(args)
        try:
            return [json.loads(line) for line in out.splitlines() if line.strip()]
        except json.JSONDecodeError:
            msg = "gh api returned output that is not JSON"
            raise MonitorError(msg) from None

    def list_open_alerts(self) -> list[Alert]:
        """Every open alert, all pages. Raises on any failure: never an empty all-clear."""
        raws = self._objects(
            [
                "api",
                f"repos/{self.repo}/dependabot/alerts?state=open&per_page=100",
                "--paginate",
                "--jq",
                f".[] | {ALERT_JQ}",
            ]
        )
        return [parse_alert(raw) for raw in raws]

    def get_alert(self, number: int) -> Alert:
        """A fresh read of one alert, whatever its state."""
        raws = self._objects(
            ["api", f"repos/{self.repo}/dependabot/alerts/{number}", "--jq", ALERT_JQ]
        )
        if len(raws) != 1:
            msg = f"alert {number} read returned {len(raws)} objects"
            raise MonitorError(msg)
        return parse_alert(raws[0])

    def list_tracking_issues(self) -> dict[int, TrackingIssue]:
        """Open and closed tracking issues by marker, all pages. Prefer open, then oldest."""
        raws = self._objects(
            [
                "api",
                f"repos/{self.repo}/issues?labels={TRACKING_LABEL}&state=all&per_page=100",
                "--paginate",
                "--jq",
                ISSUE_JQ,
            ]
        )
        found: dict[int, TrackingIssue] = {}
        for raw in raws:
            match = MARKER_RE.search(raw.get("body") or "")
            if not match:
                continue
            if not isinstance(raw.get("number"), int) or not isinstance(raw.get("state"), str):
                msg = "tracking issue list returned an unexpected shape"
                raise MonitorError(msg)
            candidate = TrackingIssue(raw["number"], raw["state"])
            alert = int(match.group(1))
            if alert not in found or _prefer(candidate, found[alert]):
                found[alert] = candidate
        return found

    def create_issue(self, number: int) -> int:
        body = tracking_body(number)
        out = self._run(
            [
                "api",
                "-X",
                "POST",
                f"repos/{self.repo}/issues",
                "-f",
                f"title={TRACKING_TITLE.format(number=number)}",
                "-f",
                f"body={body}",
                "-f",
                f"labels[]={TRACKING_LABEL}",
                "--jq",
                ".number",
            ]
        )
        try:
            return int(out.strip())
        except ValueError:
            msg = "issue creation did not return an issue number"
            raise MonitorError(msg) from None

    def set_issue_state(self, issue: int, state: str, comment: str) -> None:
        # State first: if the comment then fails, the next run sees a matching state and
        # does not repeat the change.
        self._run(
            ["api", "-X", "PATCH", f"repos/{self.repo}/issues/{issue}", "-f", f"state={state}"]
        )
        self._run(
            [
                "api",
                "-X",
                "POST",
                f"repos/{self.repo}/issues/{issue}/comments",
                "-f",
                f"body={comment}",
            ]
        )


def _prefer(candidate: TrackingIssue, current: TrackingIssue) -> bool:
    if (candidate.state == "open") != (current.state == "open"):
        return candidate.state == "open"
    return candidate.number < current.number


def tracking_body(number: int) -> str:
    """The whole public body of a tracking issue: a marker and a protected link."""
    return (
        f"{MARKER_TEMPLATE.format(number=number)}\n"
        "A repository security alert needs a fix. Details are deliberately not published "
        "here because this repository is public.\n\n"
        f"Protected alert (maintainers only): {ALERT_URL.format(number=number)}\n\n"
        "This item closes when GitHub reports the alert as fixed, "
        "or when a maintainer pauses tracking."
    )


# --- Local state and lock -----------------------------------------------------------


def _track_to_json(track: Track) -> dict:
    out: dict = {}
    for f in fields(Track):
        value = getattr(track, f.name)
        out[f.name] = _iso(value) if isinstance(value, datetime) else value
    return out


def _track_from_json(data: dict) -> Track:
    track = Track()
    for f in fields(Track):
        if f.name not in data:
            continue
        value = data[f.name]
        if f.name.endswith("_at"):
            value = _parse_time(value)
        setattr(track, f.name, value)
    if track.pending_dispatch not in DISPATCH_REASONS:
        track.pending_dispatch = None
    return track


def load_state(state_dir: Path) -> State:
    path = state_dir / "state.json"
    if not path.exists():
        return State()
    try:
        raw = json.loads(path.read_text())
        return State(
            last_attempt_at=_parse_time(raw.get("last_attempt_at")),
            last_success_at=_parse_time(raw.get("last_success_at")),
            last_failure_notice_at=_parse_time(raw.get("last_failure_notice_at")),
            tracks={int(k): _track_from_json(v) for k, v in raw.get("alerts", {}).items()},
        )
    except (OSError, ValueError, AttributeError, TypeError):
        msg = f"state file {path.name} is unreadable; fix or move it, it is never overwritten"
        raise MonitorError(msg) from None


def save_state(state_dir: Path, state: State) -> None:
    """Write atomically so a crash never leaves half a state file."""
    payload = {
        "version": 1,
        "last_attempt_at": _iso(state.last_attempt_at),
        "last_success_at": _iso(state.last_success_at),
        "last_failure_notice_at": _iso(state.last_failure_notice_at),
        "alerts": {str(n): _track_to_json(t) for n, t in sorted(state.tracks.items())},
    }
    tmp = state_dir / f"state.json.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
        tmp.replace(state_dir / "state.json")
    except OSError as exc:
        msg = f"state could not be written ({type(exc).__name__})"
        raise MonitorError(msg) from None


class RunLock:
    """An exclusive lock file with an expiring lease, so a crashed holder is recoverable."""

    def __init__(self, state_dir: Path, now: datetime) -> None:
        self.path = state_dir / "monitor.lock"
        self.now = now
        self.token = uuid.uuid4().hex

    def acquire(self) -> bool:
        if self._create():
            return True
        if not self._expired():
            return False
        # Move the stale lock aside, then create our own. Two runs finding the same stale
        # lock at the same instant is possible but needs a crash two hours old.
        try:
            self.path.rename(self.path.with_name(f"monitor.lock.stale.{self.token}"))
        except FileNotFoundError:
            return self._create()
        self.path.with_name(f"monitor.lock.stale.{self.token}").unlink(missing_ok=True)
        return self._create()

    def _create(self) -> bool:
        # Write the contents first, then link into place: the lock never exists empty,
        # so a racing run cannot read it half-written and mistake it for expired.
        scratch = self.path.with_name(f"monitor.lock.{self.token}.tmp")
        expires = self.now + LOCK_TTL
        scratch.write_text(json.dumps({"token": self.token, "expires_at": expires.isoformat()}))
        try:
            os.link(scratch, self.path)
        except FileExistsError:
            return False
        finally:
            scratch.unlink(missing_ok=True)
        return True

    def _expired(self) -> bool:
        try:
            expires = _parse_time(json.loads(self.path.read_text()).get("expires_at"))
        except (OSError, ValueError):
            return self._older_than_ttl()
        return expires is None or expires <= self.now

    def _older_than_ttl(self) -> bool:
        try:
            modified = datetime.fromtimestamp(self.path.stat().st_mtime, UTC)
        except OSError:
            return True
        return self.now - modified > LOCK_TTL

    def release(self) -> None:
        try:
            held = json.loads(self.path.read_text()).get("token")
        except (OSError, json.JSONDecodeError):
            return
        if held == self.token:
            self.path.unlink(missing_ok=True)


# --- Notification and dispatch ------------------------------------------------------


@dataclass(frozen=True)
class Config:
    state_dir: Path
    notify_cmd: list[str]
    dispatch_cmd: list[str]
    max_dispatch: int = DEFAULT_MAX_DISPATCH


def notify(cmd: list[str], events: list[Event]) -> None:
    """Hand the events to the private notification command as JSON on stdin."""
    payload = json.dumps({"events": [e.as_json() for e in events]})
    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            input=payload,
            capture_output=True,
            text=True,
            check=False,
            timeout=SUBPROCESS_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        msg = f"notification command could not run ({type(exc).__name__})"
        raise MonitorError(msg) from None
    if result.returncode != 0:
        msg = f"notification command exited {result.returncode}"
        raise MonitorError(msg)


def dispatch(cmd: list[str], alert: int, reason: str) -> None:
    """Start the local agent for one alert, detached. It receives only the alert number."""
    env = {
        **os.environ,
        "ARX_SECURITY_ALERT": str(alert),
        "ARX_SECURITY_REASON": reason,
        "ARX_SECURITY_BRIEF": str(BRIEF_PATH),
    }
    try:
        process = subprocess.Popen(  # noqa: S603
            [*cmd, str(alert), reason],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        msg = f"dispatch command could not start ({type(exc).__name__})"
        raise MonitorError(msg) from None
    try:
        code = process.wait(timeout=DISPATCH_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        return  # still running after the grace period: the agent started
    if code != 0:
        msg = f"dispatch command exited {code} straight away"
        raise MonitorError(msg)


# --- The check ----------------------------------------------------------------------


@dataclass
class Report:
    """What a check did, in numbers and fixed words only."""

    events: list[Event] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def gather_alerts(
    gh: GhCli, state: State, index: dict[int, TrackingIssue], errors: list[str]
) -> list[Alert]:
    """All open alerts plus a fresh read of every tracked alert that is not in that list.

    The open list must succeed or the run stops. A failed read of one tracked alert is
    recorded and skipped, so it cannot block the others.
    """
    open_alerts = {a.number: a for a in gh.list_open_alerts()}
    to_read = {n for n, t in state.tracks.items() if t.last_state != "fixed"}
    to_read |= {n for n, issue in index.items() if issue.state == "open"}
    for number in sorted(to_read - open_alerts.keys()):
        try:
            open_alerts[number] = gh.get_alert(number)
        except MonitorError as exc:
            errors.append(f"alert {number}: {exc}")
    return [open_alerts[n] for n in sorted(open_alerts)]


def _sync_issue(gh: GhCli, alert: Alert, track: Track, index: dict[int, TrackingIssue]) -> None:
    """Make the public tracking issue match what the decision wants. Idempotent."""
    existing = index.get(alert.number)
    wanted = track.wanted_issue_state
    if existing is None:
        if wanted == "open":
            track.issue = gh.create_issue(alert.number)
        return
    track.issue = existing.number
    if existing.state == wanted:
        return
    if wanted == "open":
        gh.set_issue_state(existing.number, "open", "The alert is open again.")
    elif track.exception_at is not None:
        gh.set_issue_state(existing.number, "closed", "Tracking is paused by a maintainer.")
    else:
        gh.set_issue_state(existing.number, "closed", "GitHub reports the alert as fixed.")


def run_check(gh: GhCli, config: Config, now: datetime, *, dry_run: bool) -> Report:
    """Reconcile every alert once. Public writes are idempotent; state commits last."""
    state = load_state(config.state_dir)
    state.last_attempt_at = now
    index = gh.list_tracking_issues()
    report = Report(events=missed_run_events(state, now))
    alerts = gather_alerts(gh, state, index, report.errors)
    if state.last_success_at is None and index:
        report.events.append(Event(Kind.STATE_REBUILT, detail="tracking-items-exist"))
    decided: dict[int, tuple[Alert, Track]] = {}
    for alert in alerts:
        track, events = reconcile_alert(alert, state.tracks.get(alert.number), now)
        if track is None:
            item = index.get(alert.number)
            if item is None or item.state != "open":
                continue
            # A fixed alert whose public item is still open but whose track was never saved
            # (a failed notification, a lost state directory): the fresh fixed read closes it.
            track = Track(last_state=alert.state, wanted_issue_state="closed")
        decided[alert.number] = (alert, track)
        report.events.extend(events)
    if dry_run:
        _describe(report, decided, now, config)
        return report
    _apply(Run(gh, config, now), state, decided, index, report)
    return report


def _describe(
    report: Report,
    decided: dict[int, tuple[Alert, Track]],
    now: datetime,
    config: Config,
) -> None:
    budget = config.max_dispatch
    for number, (alert, track) in sorted(decided.items()):
        age = _age_hours(alert_age(alert, now))
        action = f"issue {track.wanted_issue_state}"
        if track.pending_dispatch and not _lease_live(track, now) and budget > 0:
            action += f", dispatch ({track.pending_dispatch})"
            budget -= 1
        kinds = ",".join(str(e.kind) for e in report.events if e.alert == number) or "none"
        report.lines.append(
            f"alert {number}: state {alert.state}, age {age}h; events {kinds}; {action}"
        )
    gap = [e for e in report.events if e.kind is Kind.MISSED_RUNS]
    if gap:
        report.lines.append(f"missed runs: last good check {gap[0].age_hours}h ago")
    if not decided:
        report.lines.append("no alerts need tracking")


@dataclass(frozen=True)
class Run:
    """The collaborators and clock one check uses."""

    gh: GhCli
    config: Config
    now: datetime


def _apply(
    run: Run,
    state: State,
    decided: dict[int, tuple[Alert, Track]],
    index: dict[int, TrackingIssue],
    report: Report,
) -> None:
    config, now = run.config, run.now
    committed: dict[int, Track] = {}
    for number, (alert, track) in sorted(decided.items()):
        try:
            _sync_issue(run.gh, alert, track, index)
        except MonitorError as exc:
            report.errors.append(f"alert {number}: {exc}")
            report.events = [e for e in report.events if e.alert != number]
            continue
        committed[number] = track
    if report.events:
        # Nothing is recorded as announced unless the maintainer was actually told. A
        # broken notification command therefore also holds back the dispatches below.
        notify(config.notify_cmd, report.events)
    state.tracks.update(committed)
    _dispatch_pending(run, state, committed, report)
    state.last_attempt_at = now
    if not report.errors:
        state.last_success_at = now
        state.last_failure_notice_at = None
    save_state(config.state_dir, state)
    if report.errors:
        count = len(report.errors)
        notify_failure_if_due(config, state, now, f"{count} problem(s) in this check")


def _dispatch_pending(run: Run, state: State, committed: dict[int, Track], report: Report) -> None:
    budget = run.config.max_dispatch
    for number, track in sorted(committed.items()):
        if budget <= 0:
            break
        if not track.pending_dispatch or _lease_live(track, run.now):
            continue
        reason = track.pending_dispatch
        try:
            dispatch(run.config.dispatch_cmd, number, reason)
        except MonitorError as exc:
            report.errors.append(f"alert {number}: {exc}")
            continue
        report.lines.append(f"dispatched agent for alert {number} ({reason})")
        track.last_dispatch_at = run.now
        track.lease_expires_at = run.now + WORKER_LEASE
        track.pending_dispatch = None
        track.outcome = None
        track.outcome_reported_at = None
        budget -= 1
        # Saved at once: a crash after a spawn must not make the next run spawn again.
        save_state(run.config.state_dir, state)


def notify_failure_if_due(config: Config, state: State, now: datetime, message: str) -> bool:
    """Tell the maintainer about a failure at most once per notice interval."""
    last = state.last_failure_notice_at
    if last is not None and now - last < FAILURE_NOTICE_INTERVAL:
        return False
    notify(config.notify_cmd, [Event(Kind.FAILURE, detail=message)])
    state.last_failure_notice_at = now
    save_state(config.state_dir, state)
    return True


def record_failure(config: Config, now: datetime, message: str) -> None:
    """Record a failed run and tell the maintainer, even when the state file is unreadable."""
    try:
        state = load_state(config.state_dir)
    except MonitorError:
        # A corrupt state file must not make the monitor mute: notify without throttling.
        notify(config.notify_cmd, [Event(Kind.FAILURE, detail=f"{message}; state unreadable")])
        return
    state.last_attempt_at = now
    if not notify_failure_if_due(config, state, now, message):
        save_state(config.state_dir, state)


# --- Commands -----------------------------------------------------------------------


def resolve_config(args: argparse.Namespace, *, need_commands: bool) -> Config:
    raw_dir = args.state_dir or os.environ.get(STATE_ENV)
    if not raw_dir:
        msg = f"no state directory: pass --state-dir or set {STATE_ENV} (outside the checkout)"
        raise MonitorError(msg)
    state_dir = Path(raw_dir).expanduser().resolve()
    if state_dir == CHECKOUT_ROOT or CHECKOUT_ROOT in state_dir.parents:
        msg = "the state directory must be outside the Git checkout"
        raise MonitorError(msg)
    notify_cmd = shlex.split(os.environ.get(NOTIFY_ENV, ""))
    dispatch_cmd = shlex.split(os.environ.get(DISPATCH_ENV, ""))
    if need_commands and not (notify_cmd and dispatch_cmd):
        msg = f"a real run needs {NOTIFY_ENV} and {DISPATCH_ENV}; use --dry-run to preview"
        raise MonitorError(msg)
    return Config(state_dir, notify_cmd, dispatch_cmd, args.max_dispatch)


def _failed(config: Config, now: datetime, message: str, *, dry_run: bool) -> int:
    print(f"FAILED: {message}", file=sys.stderr)
    if not dry_run:
        record_failure(config, now, message)
    return EXIT_FAILED


def _check_locked(args: argparse.Namespace, now: datetime, gh: GhCli, config: Config) -> int:
    try:
        report = run_check(gh, config, now, dry_run=args.dry_run)
    except MonitorError as exc:
        return _failed(config, now, str(exc), dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 - an unexpected crash must still be reported
        return _failed(config, now, f"unexpected {type(exc).__name__}", dry_run=args.dry_run)
    for event in report.events:
        print(f"event: {event.kind}" + (f" alert {event.alert}" if event.alert else ""))
    for line in report.lines:
        print(line)
    for error in report.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if report.errors:
        return EXIT_ERRORS
    if not report.lines and not report.events:
        print("No change; nothing to report.")
    return EXIT_OK


def cmd_check(args: argparse.Namespace, now: datetime, gh: GhCli) -> int:
    config = resolve_config(args, need_commands=not args.dry_run)
    if args.dry_run:
        return _check_locked(args, now, gh, config)
    config.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = RunLock(config.state_dir, now)
    if not lock.acquire():
        print("Another check holds the lock; skipping this run.")
        return EXIT_OK
    try:
        return _check_locked(args, now, gh, config)
    finally:
        lock.release()


def _status_problems(state: State, now: datetime) -> list[str]:
    problems: list[str] = []
    last, attempt = state.last_success_at, state.last_attempt_at
    if last is None or now - last > MISSED_RUN_AFTER:
        problems.append("no successful check within the expected window")
    elif attempt is not None and attempt > last and now - last > CHECK_INTERVAL * 1.5:
        problems.append("the latest attempts failed after the last success")
    for number, track in sorted(state.tracks.items()):
        unresolved = track.last_state != "fixed" and track.exception_at is None
        overdue = track.detected_at is not None and now - track.detected_at >= DEADLINE
        if unresolved and overdue and track.last_dispatch_at is None:
            problems.append(f"alert {number} is past the deadline and no agent was ever started")
    return problems


def cmd_status(args: argparse.Namespace, now: datetime) -> int:
    """Prove the scheduler is armed: fails when no good check or no agent start is seen."""
    config = resolve_config(args, need_commands=False)
    state = load_state(config.state_dir)
    unresolved = [n for n, t in state.tracks.items() if t.last_state != "fixed"]
    excepted = [n for n in unresolved if state.tracks[n].exception_at]
    print(f"last attempt: {_iso(state.last_attempt_at) or 'never'}")
    print(f"last success: {_iso(state.last_success_at) or 'never'}")
    print(f"tracked unresolved: {len(unresolved)} (excepted: {len(excepted)})")
    problems = _status_problems(state, now)
    if args.probe_notify:
        if not config.notify_cmd:
            problems.append(f"{NOTIFY_ENV} is not set")
        else:
            try:
                notify(config.notify_cmd, [Event(Kind.PROBE, detail="notification probe")])
            except MonitorError as exc:
                problems.append(str(exc))
    for problem in problems:
        print(f"PROBLEM: {problem}", file=sys.stderr)
    return EXIT_STALE if problems else EXIT_OK


def _edit_track(args: argparse.Namespace, now: datetime, edit: Callable[[Track], None]) -> int:
    config = resolve_config(args, need_commands=False)
    config.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = RunLock(config.state_dir, now)
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while not lock.acquire():
        if time.monotonic() >= deadline:
            print("A check is still running; run this again shortly.", file=sys.stderr)
            return EXIT_ERRORS
        time.sleep(2)
    try:
        state = load_state(config.state_dir)
        track = state.tracks.get(args.alert)
        if track is None:
            print(f"alert {args.alert} is not tracked.", file=sys.stderr)
            return EXIT_ERRORS
        edit(track)
        save_state(config.state_dir, state)
    finally:
        lock.release()
    return EXIT_OK


def cmd_ack(args: argparse.Namespace, now: datetime) -> int:
    """The agent records that its bounded run finished, freeing the worker lease."""

    def edit(track: Track) -> None:
        track.lease_expires_at = None
        track.outcome = args.outcome

    return _edit_track(args, now, edit)


def cmd_exception(args: argparse.Namespace, now: datetime) -> int:
    """A maintainer records (or clears) an exception. The alert's timer is kept."""

    if os.environ.get("ARX_SECURITY_ALERT"):
        print(
            "An exception is a maintainer decision; the agent may not record one.", file=sys.stderr
        )
        return EXIT_FAILED

    def edit(track: Track) -> None:
        track.exception_at = None if args.clear else now
        track.exception_by = None if args.clear else args.by
        track.last_reminder_at = None
        # Clearing an exception sends the agent back to the alert; setting one stops it.
        track.pending_dispatch = (track.pending_dispatch or "changed") if args.clear else None

    return _edit_track(args, now, edit)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", help=f"local state directory (default: ${STATE_ENV})")
    parser.set_defaults(max_dispatch=DEFAULT_MAX_DISPATCH)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="reconcile alerts once")
    check.add_argument("--dry-run", action="store_true", help="print proposed work, change nothing")
    check.add_argument("--max-dispatch", type=int, default=DEFAULT_MAX_DISPATCH)
    status = sub.add_parser("status", help="exit non-zero when the check looks unarmed")
    status.add_argument("--probe-notify", action="store_true", help="also send a test event")
    ack = sub.add_parser("ack", help="the agent reports its run finished")
    ack.add_argument("alert", type=int)
    ack.add_argument("--outcome", required=True, choices=[o.value for o in Outcome])
    exc = sub.add_parser("exception", help="a maintainer records or clears an exception")
    exc.add_argument("alert", type=int)
    exc.add_argument("--by", default="maintainer")
    exc.add_argument("--clear", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None, now: datetime | None = None) -> int:
    args = build_parser().parse_args(argv)
    moment = now or datetime.now(UTC)
    try:
        if args.command == "check":
            return cmd_check(args, moment, GhCli())
        if args.command == "status":
            return cmd_status(args, moment)
        if args.command == "ack":
            return cmd_ack(args, moment)
        return cmd_exception(args, moment)
    except MonitorError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
