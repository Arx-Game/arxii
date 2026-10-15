"""The gap report lists what the journeys never executed, by package (#3657)."""

from __future__ import annotations

from coverage_gaps import Gap, gaps_from, is_left_out, render


def _report(files: dict[str, tuple[int, int]]) -> dict:
    return {
        "files": {
            path: {"summary": {"num_statements": statements, "covered_lines": executed}}
            for path, (statements, executed) in files.items()
        }
    }


def test_unreached_files_are_listed_and_setup_files_are_left_out() -> None:
    report = _report(
        {
            "src/world/conditions/services.py": (120, 0),
            "src/world/conditions/tests/test_x.py": (40, 40),
            "src/world/conditions/migrations/0001_x.py": (10, 0),
            "src/world/conditions/factories.py": (20, 0),
            "src/world/conditions/__init__.py": (0, 0),
            "src/server/conf/settings.py": (300, 0),
            "src/commands/market.py": (80, 60),
            "src/world/gm/views.py": (50, 0),
        }
    )
    gaps = gaps_from(report)
    assert [g.path for g in gaps] == ["world/conditions/services.py", "world/gm/views.py"]
    assert gaps[0].package == "world.conditions"
    assert gaps[0].percent == 0


def test_the_threshold_admits_barely_reached_files() -> None:
    report = _report({"src/commands/market.py": (100, 5), "src/commands/say.py": (100, 50)})
    assert [g.path for g in gaps_from(report, min_percent=10)] == ["commands/market.py"]


def test_is_left_out_names_the_setup_homes() -> None:
    assert is_left_out("world/x/tests/test_a.py")
    assert is_left_out("world/x/migrations/0002_b.py")
    assert is_left_out("world/x/factories.py")
    assert is_left_out("world/x/__init__.py")
    assert not is_left_out("world/x/services.py")


def test_render_groups_by_package_and_counts_unreached_statements() -> None:
    gaps = [
        Gap("world/conditions/services.py", 120, 0),
        Gap("world/conditions/handlers.py", 30, 3),
        Gap("commands/market.py", 80, 0),
    ]
    text = render(gaps, 10)
    assert "3 files in 2 packages" in text
    assert "| `world.conditions` | 2 | 147 |" in text
    assert "| `commands/market.py` | 80 | 0 (0%) |" in text
    assert render([], 0).startswith("No source file")
