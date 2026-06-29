"""Tests for reflect_damage handler + bypass_pre_apply loop guard (#1584).

SQLite-safe: bypass_pre_apply=True skips the only DAMAGE_PRE_APPLY emit;
the rest is plain health arithmetic (no DISTINCT ON). Direct factory
construction throughout — no apply_condition calls.

Four cases:
  1. Primary bounce: ENEMY CombatOpponent attacker → payload.amount==0,
     opponent health drops by the reflected amount, anima cost debited.
  2. Fizzle: anima.current < reactive_anima_cost → amount unchanged,
     opponent health unchanged.
  3. Unresolvable source: classify_source(None) → payload.amount==0,
     no crash, nothing else damaged.
  4. Loop safety: attacker ALSO carries Mirror Ward → exactly one health
     drop, call returns normally (bypass_pre_apply prevents re-emit).
"""

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from flows.events.payloads import DamagePreApplyPayload
from world.combat.damage_source import classify_source
from world.combat.factories import CombatOpponentFactory
from world.conditions.constants import REFLECT_CONDITION_NAME
from world.conditions.factories import ConditionInstanceFactory, ConditionTemplateFactory
from world.magic.factories import CharacterAnimaFactory
from world.magic.services.effect_handlers import reflect_damage


def _make_reflect_template(*, reactive_anima_cost: int = 2):
    """Return a ConditionTemplate seeded as Mirror Ward."""
    return ConditionTemplateFactory(
        name=REFLECT_CONDITION_NAME,
        reactive_anima_cost=reactive_anima_cost,
    )


def _make_bearer(*, anima_current: int = 10, reactive_anima_cost: int = 2):
    """Return (bearer ObjectDB, CharacterAnima, ConditionInstance) for the reflector."""
    bearer = CharacterFactory()
    anima = CharacterAnimaFactory(character=bearer, current=anima_current, maximum=10)
    template = _make_reflect_template(reactive_anima_cost=reactive_anima_cost)
    instance = ConditionInstanceFactory(condition=template, target=bearer)
    return bearer, anima, instance


class ReflectDamagePrimaryBounceTests(TestCase):
    """Primary bounce: NPC attacker → payload zeroed, opponent health drops."""

    def test_bounce_zeroes_payload_and_debits_opponent_health(self) -> None:
        """20 incoming from a MOOK → payload.amount==0, opponent health drops 20."""
        bearer, _anima, _instance = _make_bearer(anima_current=10, reactive_anima_cost=2)
        opponent = CombatOpponentFactory(health=50, soak_value=0)

        payload = DamagePreApplyPayload(
            target=bearer,
            amount=20,
            damage_type=None,
            source=classify_source(opponent),
        )

        reflect_damage(payload=payload)

        self.assertEqual(payload.amount, 0)
        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 30)  # 50 - 20

    def test_anima_cost_debited_on_successful_reflect(self) -> None:
        """Reactive anima cost is debited when reflect fires."""
        bearer, anima, _instance = _make_bearer(anima_current=10, reactive_anima_cost=2)
        opponent = CombatOpponentFactory(health=50, soak_value=0)

        payload = DamagePreApplyPayload(
            target=bearer,
            amount=20,
            damage_type=None,
            source=classify_source(opponent),
        )

        reflect_damage(payload=payload)

        anima.refresh_from_db()
        self.assertEqual(anima.current, 8)  # 10 - 2


class ReflectDamageFizzleTests(TestCase):
    """Fizzle: anima insufficient → nothing changes."""

    def test_fizzle_when_anima_below_cost(self) -> None:
        """anima.current < reactive_anima_cost → amount unchanged, opponent health unchanged."""
        bearer, _anima, _instance = _make_bearer(anima_current=1, reactive_anima_cost=2)
        opponent = CombatOpponentFactory(health=50, soak_value=0)

        payload = DamagePreApplyPayload(
            target=bearer,
            amount=20,
            damage_type=None,
            source=classify_source(opponent),
        )

        reflect_damage(payload=payload)

        self.assertEqual(payload.amount, 20)  # unchanged — fizzle
        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 50)  # unchanged


class ReflectDamageUnresolvableSourceTests(TestCase):
    """Unresolvable source: payload is zeroed, nothing else damaged."""

    def test_environment_source_zeroes_amount_no_crash(self) -> None:
        """classify_source(None) → type='environment', ref=None → payload.amount==0, no crash."""
        bearer, _anima, _instance = _make_bearer(anima_current=10, reactive_anima_cost=2)

        payload = DamagePreApplyPayload(
            target=bearer,
            amount=20,
            damage_type=None,
            source=classify_source(None),
        )

        # Must not raise; nothing external should be damaged.
        reflect_damage(payload=payload)

        self.assertEqual(payload.amount, 0)

    def test_zero_amount_guard_returns_early(self) -> None:
        """payload.amount == 0 → immediate return; no cost deducted."""
        bearer, anima, _instance = _make_bearer(anima_current=10, reactive_anima_cost=2)
        opponent = CombatOpponentFactory(health=50, soak_value=0)

        payload = DamagePreApplyPayload(
            target=bearer,
            amount=0,
            damage_type=None,
            source=classify_source(opponent),
        )

        reflect_damage(payload=payload)

        self.assertEqual(payload.amount, 0)
        anima.refresh_from_db()
        self.assertEqual(anima.current, 10)  # unchanged — early return
        opponent.refresh_from_db()
        self.assertEqual(opponent.health, 50)  # unchanged


class ReflectDamageLoopSafetyTests(TestCase):
    """Loop safety: bypass_pre_apply=True prevents re-emit on the attacker."""

    def test_bounce_is_not_re_reflected_when_attacker_has_mirror_ward(self) -> None:
        """Opponent with Mirror Ward: health drops exactly once; call returns normally.

        bypass_pre_apply=True on the apply_damage_to_opponent call skips
        DAMAGE_PRE_APPLY for the attacker, so the opponent's own reflect
        condition never fires — no infinite recursion, exactly one health drop.
        """
        bearer, _anima, _instance = _make_bearer(anima_current=10, reactive_anima_cost=2)
        opponent = CombatOpponentFactory(health=50, soak_value=0)

        # Give the opponent its own Mirror Ward condition on its objectdb.
        attacker_template = _make_reflect_template(reactive_anima_cost=2)
        ConditionInstanceFactory(condition=attacker_template, target=opponent.objectdb)

        payload = DamagePreApplyPayload(
            target=bearer,
            amount=20,
            damage_type=None,
            source=classify_source(opponent),
        )

        # Should not raise and should not recurse.
        reflect_damage(payload=payload)

        self.assertEqual(payload.amount, 0)
        opponent.refresh_from_db()
        # Health drops exactly once (by 20) — not recursed or re-bounced.
        self.assertEqual(opponent.health, 30)
