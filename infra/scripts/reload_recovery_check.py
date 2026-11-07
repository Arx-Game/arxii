#!/usr/bin/env python3
"""Drive the real Portal/Server lifecycle under real systemd (#4999).

Run by .github/workflows/reload-recovery.yml as root on a throwaway runner. It
renders the role's actual templates, then breaks a disposable Evennia game in
each way the spec lists and reports what happened, with a logged-in telnet
client as the player. It never touches production and needs no secrets.

Expectations come from the spec on #4999, not from this code's output.

Usage: reload_recovery_check.py setup | run [scenario ...]
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import http.server
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import time
import tomllib

from jinja2 import Environment, FileSystemLoader, StrictUndefined
import yaml

REPO = Path(__file__).resolve().parents[2]
ROLE = REPO / "infra/ansible/roles/app_deploy"
DEFAULTS = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
APP_USER = DEFAULTS["app_user"]
SERVICE = DEFAULTS["app_service"]
UNIT = f"{SERVICE}.service"
PROJECT = Path(DEFAULTS["app_current"])
GAMEDIR = Path(DEFAULTS["app_gamedir"])
SERVER_PIDFILE = Path(DEFAULTS["app_pidfile"])
PORTAL_PIDFILE = Path(DEFAULTS["app_portal_pidfile"])
SERVER_PORT = int(DEFAULTS["app_server_web_port"])
EVIDENCE_DIR = Path(DEFAULTS["app_reload_evidence_dir"])
UV = "/usr/local/bin/uv"
ENV_FILE = Path("/etc/arxii/arxii.env")
ALERT_PORT = 8999
ALERT_LOG = Path("/tmp/arxii-alerts.log")  # noqa: S108 - throwaway runner
TELNET_PORT = 4000
ROOM_TEXT = b"Limbo"
SUPERUSER = "recoverycheck"
# Synthetic: the game exists for the length of this job and has no other account.
SUPERUSER_PASSWORD = "synthetic-disposable-password"  # noqa: S105
# Words the alerts and evidence carry, per the spec's scenarios.
ALERT_RECOVERED = "recovered"
ALERT_EXHAUSTED = "exhausted"
ALERT_RESTARTED = "restarted"
ALERT_STILL_DOWN = "still down"
ALERT_UNCLEAN = "stopped uncleanly"
HOLDER_COMMAND = "python3"
ACTIVE = "active"
INACTIVE = "inactive"
SYSTEMD_INIT = "systemd"
NAME_KEY = "name"
EVENNIA_PACKAGE = "evennia"
SETUPTOOLS_PACKAGE = "setuptools"
SETUP_COMMAND = "setup"
RESTART_STAMP = Path("/run/arxii-watchdog.restart-stamp")
# Ruled in #4999, plus margin for scheduling on a shared runner.
RELOAD_BUDGET_S = 200


PUPPET_SYNC = """

def _with_puppet_sync(original):
    def puppet_object(self, session, obj):
        original(self, session, obj)
        import evennia

        if session.puppet is obj:
            evennia.SESSION_HANDLER.session_portal_sync(session)

    return puppet_object


Account.puppet_object = _with_puppet_sync(Account.puppet_object)
"""


def sh(cmd: str, *, check: bool = True, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    """Run a shell command, echoing it so the job log reads as a transcript."""
    print(f"$ {cmd}", flush=True)
    result = subprocess.run(  # noqa: S602 - fixed commands on a throwaway runner
        cmd, shell=True, text=True, capture_output=True, timeout=timeout, check=False
    )
    if result.stdout.strip():
        print(result.stdout.rstrip(), flush=True)
    if result.stderr.strip():
        print(result.stderr.rstrip(), flush=True)
    if check and result.returncode != 0:
        msg = f"exit {result.returncode}: {cmd}"
        raise RuntimeError(msg)
    return result


def as_app(cmd: str, **kwargs) -> subprocess.CompletedProcess[str]:
    return sh(f"sudo -H -u {APP_USER} bash -c {shlex.quote(cmd)}", **kwargs)


def render(template: str, **extra) -> str:
    # Rendering shell and unit files, never HTML.
    env = Environment(  # noqa: S701
        loader=FileSystemLoader(ROLE / "templates"),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    context = {
        **{k: v for k, v in DEFAULTS.items() if isinstance(v, (str, int, bool))},
        "base_uv_bin": UV,
        **extra,
    }
    return env.get_template(template).render(context)


def setup() -> None:
    """Install a disposable game laid out the way the role lays out production."""
    init = sh("ps -p 1 -o comm=").stdout.strip()
    if init != SYSTEMD_INIT:
        msg = f"PID 1 is {init!r}; this test means nothing without real systemd"
        raise RuntimeError(msg)
    sh("systemctl --version | head -n1")
    sh(f"id {APP_USER} || useradd -m -s /bin/bash {APP_USER}")
    PROJECT.mkdir(parents=True, exist_ok=True)
    lock = tomllib.loads((REPO / "uv.lock").read_text())
    evennia = next(p for p in lock["package"] if p[NAME_KEY] == EVENNIA_PACKAGE)
    # Evennia's launcher still imports distutils, which only setuptools provides now.
    setuptools = next(p for p in lock["package"] if p[NAME_KEY] == SETUPTOOLS_PACKAGE)["version"]
    # uv.lock spells it "<url>?<query>#<sha>"; pin the same commit production runs.
    url, _, sha = evennia["source"]["git"].partition("#")
    git_url = url.partition("?")[0]
    (PROJECT / "pyproject.toml").write_text(
        "[project]\n"
        'name = "reload-recovery-game"\n'
        'version = "0"\n'
        'requires-python = ">=3.13,<3.14"\n'
        f'dependencies = ["evennia @ git+{git_url}@{sha}", "setuptools=={setuptools}"]\n'
        "[tool.uv]\npackage = false\n"
    )
    sh(f"chown -R {APP_USER}: {PROJECT.parent}")
    as_app(f"cd {PROJECT} && {UV} sync", timeout=1200)
    as_app(f"cd {PROJECT} && {UV} run evennia --init {GAMEDIR.name}")
    as_app(f"cd {GAMEDIR} && {UV} run evennia migrate", timeout=1200)
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text(
        f"OFFBOX_ALERT_TOKEN=http://127.0.0.1:{ALERT_PORT}/check\n"
        f"EVENNIA_SUPERUSER_USERNAME={SUPERUSER}\n"
        f"EVENNIA_SUPERUSER_PASSWORD={SUPERUSER_PASSWORD}\n"
        "EVENNIA_SUPERUSER_EMAIL=recovery@example.invalid\n"
    )
    ENV_FILE.chmod(0o600)
    install_rendered()
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    unit = next(t for t in tasks if t.get(NAME_KEY, "").startswith("Install the watchdog service"))
    content = Environment(undefined=StrictUndefined).from_string(  # noqa: S701 - unit file
        unit["ansible.builtin.copy"]["content"]
    )
    Path("/etc/systemd/system/arxii-watchdog.service").write_text(
        content.render(secrets_env_file=str(ENV_FILE))
    )
    # A mirror of the call Arx's Account makes (#4999), shaped the same way, because the
    # stock game's Account lacks it. This proves Evennia restores a synced puppet; that
    # Arx's Account makes the call is pinned by typeclasses/tests.
    accounts = GAMEDIR / "typeclasses/accounts.py"
    accounts.write_text(accounts.read_text() + PUPPET_SYNC)
    alert_src = REPO / "infra/ansible/roles/offbox_alerting/templates/arxii-alert.sh.j2"
    install_script("/usr/local/sbin/arxii-alert", alert_src.read_text())
    sh("systemctl daemon-reload")


def install_script(dest: str, content: str) -> None:
    path = Path(dest)
    path.write_text(content)
    path.chmod(0o750)


def install_rendered() -> None:
    Path(f"/etc/systemd/system/{UNIT}").write_text(
        render("arxii.service.j2", secrets_env_file=str(ENV_FILE))
    )
    install_script("/usr/local/sbin/arxii-reload", render("arxii-reload.sh.j2"))
    install_script("/usr/local/sbin/arxii-watchdog", render("arxii-watchdog.sh.j2"))


# --- What a player and an operator can observe -----------------------------------


class Player:
    """A logged-in telnet client: the connection Server-only recovery must keep."""

    def __init__(self) -> None:
        self.sock = socket.create_connection(("127.0.0.1", TELNET_PORT), timeout=15)
        self.sock.settimeout(3)
        self._drain(3)
        self.send(f"connect {SUPERUSER} {SUPERUSER_PASSWORD}")
        if ROOM_TEXT not in self._read_until(ROOM_TEXT, 30):
            msg = "login did not reach the starting room"
            raise RuntimeError(msg)

    def send(self, text: str) -> None:
        self.sock.sendall(text.encode() + b"\r\n")

    def _drain(self, seconds: float) -> None:
        self._read_until(b"\0never\0", seconds)

    def _read_until(self, wanted: bytes, seconds: float) -> bytes:
        seen = b""
        end = time.monotonic() + seconds
        while time.monotonic() < end and wanted not in seen:
            try:
                chunk = self.sock.recv(4096)
            except TimeoutError:
                continue
            if not chunk:
                msg = "the Portal closed the connection"
                raise ConnectionError(msg)
            seen += chunk
        return seen

    def still_playing(self) -> bool:
        """True when the same socket, without logging in again, gets a game answer."""
        try:
            self._drain(1)
            self.send("look")
            return ROOM_TEXT in self._read_until(ROOM_TEXT, 30)
        except OSError:
            return False

    def close(self) -> None:
        self.sock.close()


def pid_from(path: Path) -> int | None:
    try:
        pid = int(path.read_text().strip())
    except (OSError, ValueError):
        return None
    return pid if Path(f"/proc/{pid}").exists() else None


def portal() -> int | None:
    return pid_from(PORTAL_PIDFILE)


def server() -> int | None:
    return pid_from(SERVER_PIDFILE)


def unit_state() -> str:
    return sh(f"systemctl is-active {UNIT}", check=False).stdout.strip()


def main_pid() -> int:
    return int(sh(f"systemctl show -p MainPID --value {UNIT}").stdout.strip())


def wait_for(predicate: Callable[[], bool], seconds: int) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(1)
    return False


def game_is_up() -> bool:
    return unit_state() == ACTIVE and portal() is not None and server() is not None


class PortHolder:
    """A listener that is not ours to kill: a different user, on the Server's port."""

    def __init__(self, delay_release_s: float | None = None) -> None:
        self.proc: subprocess.Popen[bytes] | None = None
        self.delay_release_s = delay_release_s

    def grab(self) -> None:
        code = (
            "import socket,time;s=socket.socket();"
            "s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);"
            f"s.bind(('127.0.0.1',{SERVER_PORT}));s.listen();time.sleep(3600)"
        )
        self.proc = subprocess.Popen(  # noqa: S603 - fixed command, throwaway runner
            ["/usr/bin/python3", "-c", code]
        )
        time.sleep(1)
        if self.delay_release_s is not None:
            threading.Timer(self.delay_release_s, self.release).start()

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def release(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            self.proc.wait()


def grab_port_when_server_stops(holder: PortHolder) -> threading.Thread:
    """Take the port in the gap between the old Server stopping and the new binding."""

    old = server()

    def watch() -> None:
        end = time.monotonic() + 60
        while time.monotonic() < end:
            if old is None or not Path(f"/proc/{old}").exists():
                holder.grab()
                return
            time.sleep(0.02)

    thread = threading.Thread(target=watch)
    thread.start()
    return thread


class AlertSink(http.server.BaseHTTPRequestHandler):
    """Stands in for the off-box monitor; arxii-alert itself is the real script."""

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("content-length", 0))).decode()
        with ALERT_LOG.open("a") as handle:
            handle.write(body + "\n")
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args) -> None:
        pass


def alerts() -> str:
    return ALERT_LOG.read_text() if ALERT_LOG.exists() else ""


def run_watchdog() -> None:
    # Blocks until it finishes: the real unit, started the way the timer starts it.
    sh("systemctl start arxii-watchdog.service", check=False, timeout=900)
    sh("journalctl -u arxii-watchdog.service -n 12 --no-pager -o cat", check=False)


def grace_period_passed() -> None:
    """Age the unit past the watchdog's fresh-start grace period."""
    time.sleep(125)


def reset() -> None:
    """Every scenario starts from a clean, running game with no leftovers."""
    RESTART_STAMP.unlink(missing_ok=True)
    (GAMEDIR / "server/reboot.requested").unlink(missing_ok=True)
    shutil.rmtree(EVIDENCE_DIR, ignore_errors=True)
    install_rendered()
    sh("systemctl daemon-reload")
    sh(f"systemctl reset-failed {UNIT}", check=False)
    sh(f"systemctl restart {UNIT}", check=False, timeout=400)
    if not wait_for(game_is_up, 60):
        msg = "the game did not come up for this scenario"
        raise RuntimeError(msg)
    # After the restart: stopping the previous scenario's game can raise an alert.
    ALERT_LOG.unlink(missing_ok=True)


# --- Scenarios: each row of the spec's Verification table -------------------------


@dataclass
class Checks:
    name: str
    failures: list[str]
    notes: list[str]

    def expect(self, ok: bool, text: str) -> None:
        print(f"{'PASS' if ok else 'FAIL'}: {text}", flush=True)
        self.notes.append(f"{'saw' if ok else 'DID NOT SEE'}: {text}")
        if not ok:
            self.failures.append(text)


def clean_reload(c: Checks) -> None:
    player = Player()
    before_portal, before_server = portal(), server()
    c.expect(main_pid() == before_portal, "systemd's main process is the Portal")
    rc = sh(f"systemctl reload {UNIT}", check=False).returncode
    c.expect(rc == 0, "systemctl reload exits 0")
    c.expect(portal() == before_portal, "the Portal PID is unchanged")
    c.expect(server() not in (None, before_server), "a new Server PID")
    c.expect(player.still_playing(), "the logged-in player's next command is answered")
    c.expect(not list(EVIDENCE_DIR.glob("*.log")), "no failure evidence on a clean reload")
    c.expect(alerts() == "", "no alert on a clean reload")
    player.close()


def port_held_then_freed(c: Checks) -> None:
    player = Player()
    before_portal = portal()
    holder = PortHolder(delay_release_s=30)
    thread = grab_port_when_server_stops(holder)
    rc = sh(f"systemctl reload {UNIT}", check=False, timeout=400).returncode
    thread.join()
    c.expect(rc == 0, "systemctl reload exits 0 once the port frees")
    c.expect(portal() == before_portal, "the Portal PID is unchanged")
    c.expect(server() is not None, "a Server is running")
    c.expect(player.still_playing(), "the logged-in player's next command is answered")
    evidence = "".join(p.read_text() for p in EVIDENCE_DIR.glob("*.log"))
    c.expect(HOLDER_COMMAND in evidence, "the evidence names the process holding the port")
    c.expect(ALERT_RECOVERED in alerts(), "an alert says it failed and recovered")
    player.close()


def port_held_throughout(c: Checks) -> None:
    before_portal = portal()
    holder = PortHolder()
    thread = grab_port_when_server_stops(holder)
    started = time.monotonic()
    rc = sh(f"systemctl reload {UNIT}", check=False, timeout=400).returncode
    took = time.monotonic() - started
    thread.join()
    c.expect(rc != 0, "systemctl reload exits nonzero")
    c.expect(took <= RELOAD_BUDGET_S, f"it gave up inside the budget ({took:.0f}s)")
    c.expect(unit_state() == ACTIVE, "the unit is still active")
    c.expect(portal() == before_portal, "the Portal PID is unchanged")
    c.expect(holder.alive(), "the process holding the port was not signalled")
    c.expect(ALERT_EXHAUSTED in alerts(), "an alert says recovery ran out")
    holder.release()
    sh(f"systemctl restart {UNIT}", check=False, timeout=400)
    c.expect(wait_for(game_is_up, 60), "a full restart recovers once the port is free")


def server_hung(c: Checks) -> None:
    player = Player()
    before_portal, hung = portal(), server()
    sh(f"kill -STOP {hung}")
    rc = sh(f"systemctl reload {UNIT}", check=False, timeout=400).returncode
    c.expect(rc == 0, "systemctl reload exits 0 after ending the hung Server")
    c.expect(not Path(f"/proc/{hung}").exists(), "the hung Server is gone")
    c.expect(portal() == before_portal, "the Portal PID is unchanged")
    c.expect(player.still_playing(), "the logged-in player's next command is answered")
    player.close()


def server_killed(c: Checks) -> None:
    player = Player()
    before_portal = portal()
    grace_period_passed()
    sh(f"kill -9 {server()}")
    time.sleep(2)
    c.expect(unit_state() == ACTIVE, "the unit stays active when the Server is killed")
    c.expect(portal() == before_portal, "the kill did not take the Portal with it")
    run_watchdog()
    c.expect(portal() == before_portal, "the watchdog kept the same Portal")
    c.expect(server() is not None, "a Server is back")
    c.expect(player.still_playing(), "the logged-in player's next command is answered")
    c.expect(ALERT_RECOVERED in alerts(), "an alert says the Server was recovered")
    player.close()


def server_cannot_start(c: Checks) -> None:
    grace_period_passed()
    hook = GAMEDIR / "server/conf/at_server_startstop.py"
    original = hook.read_text()
    hook.write_text(original + "\nraise RuntimeError('deliberately broken for #4999')\n")
    sh(f"kill -9 {server()}")
    try:
        run_watchdog()
        c.expect(ALERT_EXHAUSTED in alerts(), "the reload ran out and said so")
        c.expect(ALERT_RESTARTED in alerts(), "the watchdog attempted its one full restart")
    finally:
        hook.write_text(original)


def port_held_watchdog_twice(c: Checks) -> None:
    grace_period_passed()
    holder = PortHolder()
    sh(f"kill -9 {server()}")
    time.sleep(1)
    holder.grab()
    run_watchdog()
    c.expect(ALERT_RESTARTED in alerts(), "the first run does one full restart")
    c.expect(RESTART_STAMP.exists(), "the restart is stamped")
    stamp = RESTART_STAMP.stat().st_mtime
    # Inside the same 15 minutes the game comes back and the Server dies again.
    holder.release()
    sh(f"systemctl reset-failed {UNIT}", check=False)
    sh(f"systemctl restart {UNIT}", check=False, timeout=400)
    c.expect(wait_for(game_is_up, 120), "the game comes back once the port is free")
    grace_period_passed()
    ALERT_LOG.unlink(missing_ok=True)
    before_portal = portal()
    holder = PortHolder()
    sh(f"kill -9 {server()}")
    time.sleep(1)
    holder.grab()
    run_watchdog()
    holder.release()
    c.expect(RESTART_STAMP.stat().st_mtime == stamp, "the second run does no full restart")
    c.expect(portal() == before_portal, "the second run kept the Portal")
    c.expect(ALERT_STILL_DOWN in alerts(), "the second run alerts that it is still down")


def ingame_reload_during_watchdog(c: Checks) -> None:
    player = Player()
    grace_period_passed()
    before_portal = portal()
    thread = threading.Thread(target=run_watchdog)
    # The Server is alive when the watchdog looks, so make it look mid-reload:
    # issue the reload first and start the watchdog while the Server is down.
    player.send("@reload")
    wait_for(lambda: server() is None, 15)
    thread.start()
    thread.join()
    c.expect(portal() == before_portal, "the Portal PID is unchanged")
    c.expect(server() is not None, "the reload completed by itself")
    c.expect(alerts() == "", "the watchdog took no action and sent no alert")
    c.expect(player.still_playing(), "the logged-in player's next command is answered")
    player.close()


def shutdown_stays_down(c: Checks) -> None:
    player = Player()
    player.send("@shutdown")
    c.expect(wait_for(lambda: unit_state() == INACTIVE, 90), "the unit goes inactive")
    run_watchdog()
    time.sleep(5)
    c.expect(unit_state() == INACTIVE, "it stays inactive after the watchdog runs")
    c.expect(ALERT_UNCLEAN not in alerts(), "a deliberate stop raises no alert")


def shutdown_during_recovery(c: Checks) -> None:
    grace_period_passed()
    holder = PortHolder()
    sh(f"kill -9 {server()}")
    time.sleep(1)
    holder.grab()
    thread = threading.Thread(target=run_watchdog)
    thread.start()
    # Past the 45 s re-check and into arxii-reload's budget, ask for a real stop.
    time.sleep(90)
    sh(f"systemctl stop --no-block {UNIT}")
    thread.join()
    holder.release()
    c.expect(wait_for(lambda: unit_state() == INACTIVE, 400), "the deliberate stop wins")
    time.sleep(5)
    c.expect(unit_state() == INACTIVE, "the game does not come back")
    c.expect(not RESTART_STAMP.exists(), "the watchdog did not restart it")


def reboot_request(c: Checks) -> None:
    # The stock game has no @reboot command. It writes this file and then does what
    # @shutdown does (src/evennia_extensions/reboot.py), so this is the same state.
    player = Player()
    (GAMEDIR / "server/reboot.requested").write_text(f"requested_by={SUPERUSER}\n")
    player.send("@shutdown")
    c.expect(wait_for(lambda: unit_state() == INACTIVE, 90), "the unit goes inactive")
    run_watchdog()
    c.expect(wait_for(game_is_up, 120), "the watchdog brings the game back")


def portal_killed(c: Checks) -> None:
    killed = portal()
    sh(f"kill -9 {killed}")
    c.expect(
        wait_for(lambda: portal() not in (None, killed) and game_is_up(), 120),
        "systemd restarts the unit without the watchdog",
    )
    c.expect(main_pid() == portal(), "systemd's main process is the new Portal")
    c.expect(ALERT_UNCLEAN in alerts(), "an alert says it stopped uncleanly")


def stop_and_start(c: Checks) -> None:
    sh(f"systemctl stop {UNIT}", timeout=300)
    c.expect(unit_state() == INACTIVE, "a clean stop ends inactive")
    survivors = sh(f"pgrep -u {APP_USER} -f twistd", check=False).stdout.strip()
    c.expect(survivors == "", "nothing is left running")
    c.expect(ALERT_UNCLEAN not in alerts(), "a clean stop raises no alert")
    sh(f"systemctl start {UNIT}", timeout=400)
    c.expect(game_is_up(), "start brings it back")


def upgrade_from_old_unit(c: Checks) -> None:
    """The first deploy: the new unit lands under a unit started the old way."""
    new_unit = Path(f"/etc/systemd/system/{UNIT}").read_text()
    old_unit = new_unit.replace(f"PIDFile={PORTAL_PIDFILE}", f"PIDFile={SERVER_PIDFILE}")
    old_unit = re.sub(
        r"^ExecReload=.*$", f"ExecReload={UV} run evennia reload", old_unit, flags=re.MULTILINE
    )
    Path(f"/etc/systemd/system/{UNIT}").write_text(old_unit)
    sh("systemctl daemon-reload")
    sh(f"systemctl restart {UNIT}", timeout=400)
    wait_for(game_is_up, 60)
    player = Player()
    before_portal = portal()
    c.expect(main_pid() == server(), "before the upgrade, the main process is the Server")
    Path(f"/etc/systemd/system/{UNIT}").write_text(new_unit)
    sh("systemctl daemon-reload")
    rc = sh(f"systemctl reload {UNIT}", check=False, timeout=400).returncode
    c.expect(rc == 0, "the first reload under the new unit exits 0")
    c.expect(portal() == before_portal, "the Portal PID is unchanged")
    c.expect(main_pid() == before_portal, "the main process is now the Portal")
    c.expect(player.still_playing(), "the logged-in player's next command is answered")
    player.close()


SCENARIOS: dict[str, Callable[[Checks], None]] = {
    "clean reload": clean_reload,
    "first deploy, old unit to new": upgrade_from_old_unit,
    "port held, freed after 30 s": port_held_then_freed,
    "port held throughout": port_held_throughout,
    "Server hung": server_hung,
    "Server killed, watchdog runs": server_killed,
    "Server cannot start, watchdog runs": server_cannot_start,
    "port held, watchdog runs twice": port_held_watchdog_twice,
    "in-game reload during the watchdog's re-check": ingame_reload_during_watchdog,
    "@shutdown stays down": shutdown_stays_down,
    "stop requested during recovery": shutdown_during_recovery,
    "@reboot request": reboot_request,
    "Portal killed": portal_killed,
    "stop then start": stop_and_start,
}


def run(selected: list[str]) -> int:
    sink = http.server.ThreadingHTTPServer(("127.0.0.1", ALERT_PORT), AlertSink)
    threading.Thread(target=sink.serve_forever, daemon=True).start()
    results: list[Checks] = []
    for name, scenario in SCENARIOS.items():
        if selected and name not in selected:
            continue
        print(f"\n===== {name} =====", flush=True)
        checks = Checks(name, [], [])
        try:
            reset()
            scenario(checks)
        except Exception as exc:  # noqa: BLE001 - report it and run the other scenarios
            checks.expect(False, f"scenario stopped early: {exc}")
        results.append(checks)
        evidence = list(EVIDENCE_DIR.glob("*.log")) if EVIDENCE_DIR.exists() else []
        for path in evidence:
            print(f"--- evidence {path.name}\n{path.read_text()}", flush=True)
        print(f"--- alerts\n{alerts()}", flush=True)
        if checks.failures:
            sh(f"journalctl -u {UNIT} -n 40 --no-pager -o short-iso", check=False)

    summary = ["| Scenario | Result | What was seen |", "|---|---|---|"]
    for checks in results:
        verdict = "FAIL" if checks.failures else "PASS"
        summary.append(f"| {checks.name} | {verdict} | {'; '.join(checks.notes)} |")
    report = "\n".join(summary) + "\n"
    print(f"\n{report}", flush=True)
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with Path(target).open("a") as handle:
            handle.write(report)
    return 1 if any(c.failures for c in results) else 0


def main() -> int:
    if sys.argv[1:2] not in (["setup"], ["run"]):
        print(__doc__)
        return 2
    if sys.argv[1] == SETUP_COMMAND:
        setup()
        return 0
    return run(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
