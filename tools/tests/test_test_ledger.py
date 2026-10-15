"""The ledger's first pass grades a module from its own text (#3657).

U-keep: grading heuristics over test source; no journey reaches tooling over text.
"""

from __future__ import annotations

from pathlib import Path

from test_ledger import app_test_modules, grade_module, ledger_for, propose, summary


def _module(tmp_path: Path, name: str, body: str) -> Path:
    tests = tmp_path / "world" / "things" / "tests"
    tests.mkdir(parents=True, exist_ok=True)
    (tests / "__init__.py").write_text("")
    path = tests / name
    path.write_text(body)
    return path


def test_a_harness_journey_is_graded_j(tmp_path: Path) -> None:
    path = _module(
        tmp_path,
        "test_journey.py",
        "from integration_tests.harness import JourneyCase\n"
        "class ASay(JourneyCase):\n"
        "    def test_heard(self):\n"
        "        told = self.telnet(self.ysmay, 'say hi')\n"
        "        self.assertIn('You say', told)\n",
    )
    row = grade_module(path, "world.things.tests.test_journey", "world.things")
    assert row.layer == "J"
    assert row.tests == 1
    assert row.journey_seams >= 1


def test_a_by_hand_cmd_test_is_a_journey_to_move(tmp_path: Path) -> None:
    path = _module(
        tmp_path,
        "test_cmd.py",
        "from unittest.mock import MagicMock\n"
        "class T(TestCase):\n"
        "    def test_runs(self):\n"
        "        cmd = CmdX(); cmd.caller = c; cmd.args = ''\n"
        "        c.msg = MagicMock()\n"
        "        cmd.func()\n"
        "        self.assertIn('done', c.msg.call_args[0][0])\n",
    )
    row = grade_module(path, "world.things.tests.test_cmd", "world.things")
    assert row.layer == "J"
    assert "before the harness" in row.reason


def test_smoke_only_modules_are_removal_candidates(tmp_path: Path) -> None:
    path = _module(
        tmp_path,
        "test_models.py",
        "class T(TestCase):\n"
        "    def test_str(self):\n"
        "        self.assertEqual(str(ThingFactory()), 'Thing')\n"
        "    def test_factory_builds(self):\n"
        "        self.assertTrue(ThingFactory().pk)\n",
    )
    row = grade_module(path, "world.things.tests.test_models", "world.things")
    assert row.layer == "R"
    assert row.reason.startswith("smoke")


def test_mock_pinned_modules_are_removal_candidates(tmp_path: Path) -> None:
    path = _module(
        tmp_path,
        "test_svc.py",
        "from unittest.mock import patch\n"
        "class T(TestCase):\n"
        "    def test_calls(self):\n"
        "        with patch('a.b') as b:\n"
        "            run()\n"
        "        b.assert_called_once()\n"
        "    def test_calls_again(self):\n"
        "        with patch('a.c') as c:\n"
        "            run()\n"
        "        c.assert_called_once_with(1)\n",
    )
    row = grade_module(path, "world.things.tests.test_svc", "world.things")
    assert row.layer == "R"
    assert row.reason.startswith("mock-pinned")


def test_cross_system_modules_are_x(tmp_path: Path) -> None:
    path = _module(
        tmp_path,
        "test_flow.py",
        "from world.scenes.services import start_scene\n"
        "from world.magic.services.resonance import grant_resonance\n"
        "class T(TestCase):\n"
        "    def test_cast_grants(self):\n"
        "        grant_resonance(start_scene())\n"
        "        self.assertEqual(ledger.total, 3)\n",
    )
    row = grade_module(path, "world.things.tests.test_flow", "world.things")
    assert row.layer == "X"
    assert row.world_packages_imported == 2


def test_own_app_imports_do_not_count_as_cross_system(tmp_path: Path) -> None:
    path = _module(
        tmp_path,
        "test_own.py",
        "from world.things.services import do\n"
        "from world.things.models import Thing\n"
        "class T(TestCase):\n"
        "    def test_do(self):\n"
        "        self.assertEqual(do(), 1)\n",
    )
    row = grade_module(path, "world.things.tests.test_own", "world.things")
    assert row.layer == "U-keep"
    assert row.world_packages_imported == 0


def test_propose_keeps_the_default_when_signals_are_quiet() -> None:
    quiet = {
        "tests": 3,
        "hypothesis": False,
        "journey_seams": 0,
        "by_hand_cmd": 0,
        "smoke_named": 1,
        "builtin_named": 0,
        "mock_asserts": 0,
        "outcome_asserts": 5,
        "shape_asserts": 0,
        "world_packages_imported": 1,
        "api_seams": 0,
    }
    layer, reason = propose(quiet)
    assert layer == "U-keep"
    assert "person decides" in reason


def test_ledger_walks_the_tests_package_and_summarises(tmp_path: Path) -> None:
    _module(tmp_path, "test_a.py", "class T(TestCase):\n    def test_str(self):\n        pass\n")
    _module(tmp_path, "test_b.py", "def helper():\n    pass\n")
    modules = app_test_modules("world.things", tmp_path)
    assert [m for _, m in modules] == ["world.things.tests.test_a", "world.things.tests.test_b"]
    rows = ledger_for("world.things", tmp_path)
    text = summary(rows)
    assert text.startswith("2 modules, 1 tests")
    assert "R" in text
    assert "U-keep" in text
