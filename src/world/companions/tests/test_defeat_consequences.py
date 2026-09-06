"""Tests for companion defeat consequence gating (#1873)."""

from django.test import TestCase, override_settings
from evennia.utils.create import create_object

from typeclasses.companions import CompanionObject
from world.combat.constants import RiskLevel
from world.companions.defeat_content import (
    SAVAGED_CONDITION_NAME,
    ensure_companion_defeat_conditions,
)
from world.companions.factories import CompanionFactory
from world.companions.factories_combat import (
    COMPANION_DIE_LABEL,
    COMPANION_RECOVER_LABEL,
    COMPANION_STAY_INCAPACITATED_LABEL,
    create_companion_defeat_pool,
)
from world.companions.models import Companion
from world.companions.services import resolve_companion_defeat


def _present_companion(**kwargs) -> Companion:
    """A CompanionFactory instance with a live CompanionObject."""
    companion = CompanionFactory(**kwargs)
    obj = create_object(CompanionObject, key=companion.name, nohome=True)
    companion.objectdb = obj
    companion.save(update_fields=["objectdb"])
    return companion


def _force_draw(pool, label: str) -> None:
    """Zero every other consequence's weight so *label* is always drawn.

    Uses ConsequencePoolEntry.weight_override rather than patching the RNG:
    ConsequencePoolEntry.Meta has no ordering, so a cumulative-weight boundary
    computed from iteration order is not guaranteed to hold (it would pass on
    SQLite and could flake on Postgres). Call this before anything reads
    pool.cached_consequences - it is a cached_property, so once computed it
    will not reflect these overrides.
    """
    from actions.models import ConsequencePoolEntry

    entries = ConsequencePoolEntry.objects.filter(pool=pool).select_related("consequence")
    for entry in entries:
        if entry.consequence.label != label:
            entry.weight_override = 0
            entry.save(update_fields=["weight_override"])


class CompanionDefeatConsequenceTests(TestCase):
    def setUp(self) -> None:
        self.pool = create_companion_defeat_pool()

    def test_low_risk_defeat_leaves_companion_active(self):
        companion = CompanionFactory()
        died = resolve_companion_defeat(companion, RiskLevel.LOW)
        companion.refresh_from_db()
        self.assertFalse(died)
        self.assertTrue(companion.is_active)

    def test_moderate_risk_defeat_leaves_companion_active(self):
        companion = CompanionFactory()
        died = resolve_companion_defeat(companion, RiskLevel.MODERATE)
        companion.refresh_from_db()
        self.assertFalse(died)
        self.assertTrue(companion.is_active)

    def test_high_risk_defeat_leaves_companion_active(self):
        companion = CompanionFactory()
        died = resolve_companion_defeat(companion, RiskLevel.HIGH)
        companion.refresh_from_db()
        self.assertFalse(died)
        self.assertTrue(companion.is_active)

    def test_extreme_risk_forces_stay_incapacitated(self):
        """EXTREME reaches the same pool as LETHAL - exercise it with a real assertion.

        This used to only assert "no exception raised", which is a tautology
        (is_active is always True or False). Forcing the draw gives it a
        specific, checkable outcome instead.
        """
        _force_draw(self.pool, COMPANION_STAY_INCAPACITATED_LABEL)
        companion = CompanionFactory()

        died = resolve_companion_defeat(companion, RiskLevel.EXTREME)

        companion.refresh_from_db()
        self.assertFalse(died)
        self.assertTrue(companion.is_active)

    def test_lethal_risk_can_release_companion(self):
        """Run enough lethal draws that at least one releases a companion.

        The die weight is 1 out of 6 total (2+3+1), so P(die) roughly 1/6 per
        draw. With 50 draws, P(no death) = (5/6)^50 roughly 0.0001 - effectively
        zero.
        """
        released_count = 0
        for _ in range(50):
            companion = CompanionFactory()
            died = resolve_companion_defeat(companion, RiskLevel.LETHAL)
            if died:
                released_count += 1
                companion.refresh_from_db()
                self.assertFalse(companion.is_active)
                self.assertIsNotNone(companion.released_at)
        self.assertGreater(released_count, 0)


class CompanionDefeatPoolIsAuthoredContentTests(TestCase):
    def test_resolve_does_not_create_the_pool(self):
        """An unseeded database gets no pool minted at draw time."""
        from actions.models import ConsequencePool
        from world.companions.factories_combat import COMPANION_DEFEAT_POOL_NAME

        companion = CompanionFactory()
        died = resolve_companion_defeat(companion, RiskLevel.LETHAL)

        self.assertFalse(died)
        self.assertFalse(ConsequencePool.objects.filter(name=COMPANION_DEFEAT_POOL_NAME).exists())


@override_settings(SEED_SAMPLE_CONTENT=True)
class SavagedOutcomeTests(TestCase):
    """Gates on SEED_SAMPLE_CONTENT (#2698).

    The fast test tier has no content repo, so ensure_companion_defeat_conditions()
    needs sample content enabled here to actually invent the Savaged row -
    authored_or_sample() no-ops without it.
    """

    def setUp(self) -> None:
        self.pool = create_companion_defeat_pool()
        ensure_companion_defeat_conditions()

    def test_stay_incapacitated_applies_savaged(self):
        from world.conditions.models import ConditionTemplate
        from world.conditions.services import has_condition

        _force_draw(self.pool, COMPANION_STAY_INCAPACITATED_LABEL)
        companion = _present_companion()

        died = resolve_companion_defeat(companion, RiskLevel.LETHAL)

        self.assertFalse(died)
        companion.refresh_from_db()
        self.assertTrue(companion.is_active)
        savaged = ConditionTemplate.get_by_name(SAVAGED_CONDITION_NAME)
        self.assertTrue(has_condition(companion.objectdb, savaged))

    def test_recover_applies_nothing(self):
        from world.conditions.models import ConditionTemplate
        from world.conditions.services import has_condition

        _force_draw(self.pool, COMPANION_RECOVER_LABEL)
        companion = _present_companion()

        died = resolve_companion_defeat(companion, RiskLevel.LETHAL)

        self.assertFalse(died)
        savaged = ConditionTemplate.get_by_name(SAVAGED_CONDITION_NAME)
        self.assertFalse(has_condition(companion.objectdb, savaged))

    def test_die_releases_and_applies_no_condition(self):
        _force_draw(self.pool, COMPANION_DIE_LABEL)
        companion = _present_companion()

        died = resolve_companion_defeat(companion, RiskLevel.LETHAL)

        self.assertTrue(died)
        companion.refresh_from_db()
        self.assertFalse(companion.is_active)
        self.assertIsNone(companion.objectdb)
