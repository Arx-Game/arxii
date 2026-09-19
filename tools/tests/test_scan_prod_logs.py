"""Tests for the bounded, read-only production log scanner."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys

SCRIPT = Path(__file__).parents[2] / "infra/scripts/scan_prod_logs.py"
LOADER = importlib.machinery.SourceFileLoader("scan_prod_logs", str(SCRIPT))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
scan_prod_logs = importlib.util.module_from_spec(SPEC)
sys.modules[LOADER.name] = scan_prod_logs
LOADER.exec_module(scan_prod_logs)


def test_extracts_separate_tracebacks_and_redacts_credentials() -> None:
    lines = [
        "[ERROR] Traceback (most recent call last):",
        '  File "one.py", line 1, in run',
        "ValueError: token=do-not-print",
        "[INFO] unrelated line",
        "Traceback (most recent call last):",
        '  File "two.py", line 2, in run',
        "TypeError: wrong type",
    ]

    matches = scan_prod_logs.extract_tracebacks(lines, source="server.log", max_matches=20)

    assert len(matches) == 2
    assert "token=<redacted>" in matches[0].text
    assert matches[0].start_line == 1
    assert "wrong type" in matches[1].text


def test_local_scan_is_bounded_and_emits_json(tmp_path: Path, capsys) -> None:
    path = tmp_path / "server.log"
    path.write_text(
        "prefix\n" * 20
        + "Traceback (most recent call last):\n"
        + '  File "x.py", line 1, in f\n'
        + "RuntimeError: broken\n"
    )

    assert scan_prod_logs.main(["--file", str(path), "--tail-bytes", "200", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scanned_sources"] == [str(path)]
    assert len(payload["tracebacks"]) == 1


def test_remote_discovery_accepts_only_direct_server_logs(monkeypatch) -> None:
    def fake_run(_target: str, _args: list[str]) -> bytes:
        return (
            b"/var/log/arxii/server.log\n"
            b"/var/log/arxii/server.log.2026_09_18\n"
            b"/var/log/arxii/server.log.2026_09_17\n"
            b"/var/log/arxii/portal.log\n"
            b"/var/log/arxii/server.log/child\n"
        )

    monkeypatch.setattr(scan_prod_logs, "_run_ssh", fake_run)
    assert scan_prod_logs.discover_remote_logs(target="arxii-prod", days=2, max_files=4) == [
        "server.log",
        "server.log.2026_09_18",
        "server.log.2026_09_17",
    ]
