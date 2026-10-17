"""The seed-factory linter rejects test factories in production code, with the
CheckOutcomeFactory random-level case rejected everywhere (#4378)."""

from lint_seed_factory import find_violations

SEED_PATH = "src/world/seeds/foo.py"


def test_outcome_factory_without_level_is_flagged_in_a_seed():
    source = "outcome = CheckOutcomeFactory(name='Success')\n"
    assert [line for line, _ in find_violations(SEED_PATH, source)] == [1]


def test_outcome_factory_without_level_is_flagged_in_a_factory_module():
    source = "def helper():\n    return CheckOutcomeFactory(name='Success')\n"
    assert [line for line, _ in find_violations("src/world/x/factories.py", source)] == [2]


def test_outcome_factory_with_explicit_level_is_allowed_in_a_factory_module():
    source = "CheckOutcomeFactory(name='Success', success_level=1)\n"
    assert find_violations("src/world/x/factories.py", source) == []


def test_any_factory_in_a_non_factory_module_is_flagged():
    assert [line for line, _ in find_violations(SEED_PATH, "GiftFactory(name='x')\n")] == [1]


def test_factory_in_a_factory_module_is_allowed():
    assert find_violations("src/world/x/factories.py", "GiftFactory(name='x')\n") == []


def test_tests_are_not_checked():
    assert find_violations("src/world/x/tests/test_a.py", "CheckOutcomeFactory()\n") == []


def test_grandfathered_module_is_allowed_but_not_for_outcome_without_level():
    path = "src/world/seeds/game_content/social.py"
    assert find_violations(path, "CheckRankFactory(rank=0)\n") == []
    assert find_violations(path, "CheckOutcomeFactory(name='x')\n") != []


def test_suppression_token_skips_the_line():
    source = "GiftFactory(name='x')  # noqa: SEED_FACTORY seeded for the E2E fixture\n"
    assert find_violations(SEED_PATH, source) == []
