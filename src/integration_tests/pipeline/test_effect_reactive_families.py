"""SQLite-safe per-family E2Es for the three DAMAGE_PRE_APPLY reactive defenses (#1584).

Proves each interceptor fires end-to-end through the REAL damage pipeline:
  apply_damage_to_participant(bearer, damage, source=enemy)
    → DAMAGE_PRE_APPLY emitted at bearer's room
    → installed Trigger fires → FlowDefinition → handler (blink_dodge /
      reflect_damage / absorb_pool)
    → effect (dodge / reflect / absorb)

SQLite-safe pattern — bypasses the PG-only apply_condition DISTINCT ON:
  1. ``ensure_*_content()`` seeds the bundle (get_or_create, idempotent).
  2. ``ConditionInstanceFactory`` creates the condition row on the bearer DIRECTLY.
  3. ``_install_reactive_side_effects`` installs live Trigger rows + notifies the
     in-memory TriggerHandler — NO apply_condition call, no DISTINCT ON.
  4. ``apply_damage_to_participant`` drives a REAL attack through the event system.

NO ``@tag("postgres")``.  These tests MUST pass on the SQLite fast tier.
Mirror of setUp pattern from test_effect_summon_telnet_e2e.py.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from evennia.objects.models import ObjectDB
from evennia.utils.idmapper import models as idmapper_models

from world.areas.positioning.factories import PositionFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import CombatAllegiance, OpponentTier
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.services import apply_damage_to_participant
from world.conditions.constants import (
    BLINK_CONDITION_NAME,
    FORCE_FIELD_CONDITION_NAME,
    REFLECT_CONDITION_NAME,
)
from world.conditions.factories import ConditionInstanceFactory, DamageSuccessLevelMultiplierFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.conditions.services import _install_reactive_side_effects
from world.magic.effect_palette_content import (
    ensure_blink_content,
    ensure_force_field_content,
    ensure_reflect_content,
)
from world.magic.factories import CharacterAnimaFactory
from world.vitals.models import CharacterVitals


class BlinkDodgeReactiveE2ETests(TestCase):
    """Phase Step blink_dodge fires at priority 30 — full damage avoidance.

    SQLite-safe: condition installed via _install_reactive_side_effects, NOT
    apply_condition. Mutation-only: a successful blink sets payload.amount=0, which
    zeroes the damage and makes lower-priority interceptors no-op (they guard on
    payload.amount<=0). No CANCEL_EVENT — see #1584 Task 16 (it would fire even on
    the anima-cost fizzle path).
    """

    def setUp(self) -> None:
        idmapper_models.flush_cache()

        # Damage multiplier rows required by apply_damage_to_participant
        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

        # Seed the Phase Step bundle (idempotent)
        ensure_blink_content()

        # Encounter + bearer participant
        self.encounter = CombatEncounterFactory()
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
        )

        # Place bearer in the encounter's room (required for DAMAGE_PRE_APPLY emit)
        self.room = ObjectDB.objects.get(pk=self.encounter.room_id)
        self.character = self.sheet.character
        self.character.location = self.room
        self.character.save()

        # Health
        CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=100,
            max_health=100,
        )

        # Anima: 20 current (blink costs 2)
        CharacterAnimaFactory(
            character=self.character,
            current=20,
            maximum=20,
        )

        # Two positions in the room so blink can relocate
        self.pos_a = PositionFactory(room=self.room, name="ground")
        self.pos_b = PositionFactory(room=self.room, name="balcony")

        # Enemy opponent as attacker
        self.enemy = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            allegiance=CombatAllegiance.ENEMY,
        )

        # Fetch the seeded ConditionTemplate by the stable name constant
        self.blink_template = ConditionTemplate.objects.get(name=BLINK_CONDITION_NAME)

    def _install_blink(self) -> ConditionInstance:
        """Create a blink ConditionInstance and install its reactive trigger."""
        inst = ConditionInstanceFactory(
            condition=self.blink_template,
            target=self.character,
        )
        _install_reactive_side_effects(self.character, self.blink_template, inst)
        # on_trigger_added defers its cache reset to transaction.on_commit, which
        # never fires inside a TestCase (the transaction is rolled back). Combat's
        # resolve_round calls trigger_handler.refresh() for the same reason before
        # resolving attacks; mirror that so the just-installed trigger is visible to
        # the next DAMAGE_PRE_APPLY dispatch in this transaction.
        self.character.trigger_handler.refresh()
        return inst

    def test_blink_dodges_attack_when_anima_sufficient(self) -> None:
        """Bearer has ≥ cost anima and ≥ 2 positions → damage_dealt == 0 + position moved."""
        from world.areas.positioning.services import position_of

        # Install blink condition + trigger
        self._install_blink()

        # Place the bearer at pos_a before the attack
        from world.areas.positioning.services import force_move_to_position

        force_move_to_position(self.character, self.pos_a)

        result = apply_damage_to_participant(
            self.participant, 30, damage_type=None, source=self.enemy
        )

        # Attack fully avoided: blink sets payload.amount=0 (mutation-only)
        self.assertEqual(
            result.damage_dealt,
            0,
            "blink_dodge should zero damage_dealt (payload.amount=0)",
        )

        # Bearer should have relocated (flavor: any position != pos_a)
        after_pos = position_of(self.character)
        self.assertIsNotNone(after_pos, "bearer should be at some position after blink")
        self.assertNotEqual(
            after_pos.pk,
            self.pos_a.pk,
            "bearer should have moved to a different position after blink",
        )

    def test_blink_fizzles_when_anima_insufficient(self) -> None:
        """Anima < cost → blink_dodge no-ops → attack lands (damage_dealt > 0)."""
        # Drain anima below the cost (Phase Step costs 2)
        from world.magic.models.anima import CharacterAnima

        anima = CharacterAnima.objects.get(character=self.character)
        anima.current = 1  # below cost=2
        anima.save(update_fields=["current"])

        self._install_blink()

        result = apply_damage_to_participant(
            self.participant, 30, damage_type=None, source=self.enemy
        )

        # Attack should land when blink cannot be afforded
        self.assertGreater(
            result.damage_dealt,
            0,
            "attack should land when bearer cannot afford blink_dodge",
        )


class ReflectDamageReactiveE2ETests(TestCase):
    """Mirror Ward reflect_damage fires at priority 20 — bounce back to attacker.

    SQLite-safe: installed via _install_reactive_side_effects. Mutation-only:
    reflect_damage sets payload.amount=0 on success (no CANCEL_EVENT, #1584 Task 16).
    The enemy CombatOpponent is passed as ``source`` so
    reflect_damage can apply_damage_to_opponent with bypass_pre_apply=True.
    """

    def setUp(self) -> None:
        idmapper_models.flush_cache()

        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

        # Seed the Mirror Ward bundle (idempotent)
        ensure_reflect_content()

        # Encounter + bearer participant
        self.encounter = CombatEncounterFactory()
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
        )

        # Place bearer in the encounter's room
        self.room = ObjectDB.objects.get(pk=self.encounter.room_id)
        self.character = self.sheet.character
        self.character.location = self.room
        self.character.save()

        # Health
        CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=100,
            max_health=100,
        )

        # Anima: 20 current (reflect costs 2)
        CharacterAnimaFactory(
            character=self.character,
            current=20,
            maximum=20,
        )

        # Enemy opponent as attacker; health we can check after reflect
        self.enemy = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            allegiance=CombatAllegiance.ENEMY,
        )

        # Fetch the seeded ConditionTemplate
        self.reflect_template = ConditionTemplate.objects.get(name=REFLECT_CONDITION_NAME)

    def test_reflect_bounces_damage_to_attacker(self) -> None:
        """reflect_damage zeros bearer damage + apply damage to the ENEMY opponent."""
        inst = ConditionInstanceFactory(
            condition=self.reflect_template,
            target=self.character,
        )
        _install_reactive_side_effects(self.character, self.reflect_template, inst)
        # See BlinkDodge note: on_trigger_added's cache reset is on_commit-deferred,
        # which never fires in a rolled-back TestCase — refresh synchronously.
        self.character.trigger_handler.refresh()

        enemy_health_before = self.enemy.health

        result = apply_damage_to_participant(
            self.participant, 20, damage_type=None, source=self.enemy
        )

        # Bearer unharmed: reflect sets payload.amount=0 (mutation-only)
        self.assertEqual(
            result.damage_dealt,
            0,
            "reflect_damage should zero bearer's damage_dealt (payload.amount=0)",
        )

        # Enemy should have taken the bounced damage
        self.enemy.refresh_from_db()
        self.assertLess(
            self.enemy.health,
            enemy_health_before,
            "reflect_damage should have applied bounced damage to the ENEMY opponent",
        )


class ForceFieldAbsorbReactiveE2ETests(TestCase):
    """Aegis Field absorb_pool fires at priority 10 — buffer soak, overflow lands.

    SQLite-safe: buffer is set DIRECTLY on the instance (absorb_remaining = 20),
    not through the CONDITION_APPLIED init trigger. Force-field is mutation-only
    (no CANCEL_EVENT) — overflow still lands on the bearer.
    """

    def setUp(self) -> None:
        idmapper_models.flush_cache()

        DamageSuccessLevelMultiplierFactory(
            min_success_level=2, multiplier=Decimal("1.00"), label="Full"
        )
        DamageSuccessLevelMultiplierFactory(
            min_success_level=1, multiplier=Decimal("0.50"), label="Partial"
        )

        # Seed the Aegis Field bundle (idempotent)
        ensure_force_field_content()

        # Encounter + bearer participant
        self.encounter = CombatEncounterFactory()
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
        )

        # Place bearer in the encounter's room
        self.room = ObjectDB.objects.get(pk=self.encounter.room_id)
        self.character = self.sheet.character
        self.character.location = self.room
        self.character.save()

        # Health
        CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=100,
            max_health=100,
        )

        # Anima: 20 current (force-field costs 1 per activation)
        CharacterAnimaFactory(
            character=self.character,
            current=20,
            maximum=20,
        )

        # Enemy opponent (source; force-field doesn't need to bounce)
        self.enemy = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
            health=50,
            max_health=50,
            allegiance=CombatAllegiance.ENEMY,
        )

        # Fetch the seeded ConditionTemplate
        self.ff_template = ConditionTemplate.objects.get(name=FORCE_FIELD_CONDITION_NAME)

    def _install_force_field(self, buffer: int = 20) -> ConditionInstance:
        """Create a force-field ConditionInstance with a pre-seeded absorb buffer."""
        inst = ConditionInstanceFactory(
            condition=self.ff_template,
            target=self.character,
        )
        inst.absorb_remaining = buffer
        inst.save(update_fields=["absorb_remaining"])
        _install_reactive_side_effects(self.character, self.ff_template, inst)
        # See BlinkDodge note: on_trigger_added's cache reset is on_commit-deferred,
        # which never fires in a rolled-back TestCase — refresh synchronously.
        self.character.trigger_handler.refresh()
        return inst

    def test_force_field_absorbs_partial_damage_and_expires(self) -> None:
        """Buffer=20, hit=30 → overflow 10 lands; buffer consumed; instance deleted."""
        inst = self._install_force_field(buffer=20)
        inst_pk = inst.pk

        result = apply_damage_to_participant(
            self.participant, 30, damage_type=None, source=self.enemy
        )

        # Bearer should have taken LESS than the raw 30 (buffer soaked 20)
        self.assertGreater(
            result.health_after,
            70,  # 100 - 30 = 70 if no buffer; any value > 70 means the buffer soaked some
            "force-field buffer should have absorbed part of the 30 damage (overflow only lands)",
        )

        # The buffer instance should have been deleted (buffer fully consumed)
        self.assertFalse(
            ConditionInstance.objects.filter(pk=inst_pk).exists(),
            "force-field ConditionInstance should be deleted when buffer reaches 0",
        )

    def test_force_field_fully_absorbs_small_hit(self) -> None:
        """Buffer=20, hit=10 → full absorption, bearer unharmed, buffer decremented."""
        inst = self._install_force_field(buffer=20)
        inst_pk = inst.pk

        result = apply_damage_to_participant(
            self.participant, 10, damage_type=None, source=self.enemy
        )

        # Bearer should take 0 effective damage (buffer absorbs all 10)
        self.assertEqual(
            result.damage_dealt,
            0,
            "absorb_pool should fully absorb a hit smaller than the buffer",
        )

        # Buffer should still exist but with 10 remaining
        inst.refresh_from_db()
        self.assertEqual(
            inst.absorb_remaining,
            10,
            "absorb_remaining should be decremented by the absorbed amount",
        )
        self.assertTrue(
            ConditionInstance.objects.filter(pk=inst_pk).exists(),
            "force-field ConditionInstance should persist when buffer not fully consumed",
        )

    def test_second_hit_after_buffer_depletion_lands_in_full(self) -> None:
        """After buffer is consumed, a second hit lands with no absorption."""
        inst = self._install_force_field(buffer=10)
        inst_pk = inst.pk

        # First hit: 10 exactly depletes the buffer
        result1 = apply_damage_to_participant(
            self.participant, 10, damage_type=None, source=self.enemy
        )
        self.assertEqual(
            result1.damage_dealt,
            0,
            "first hit should be fully absorbed by the buffer",
        )
        self.assertFalse(
            ConditionInstance.objects.filter(pk=inst_pk).exists(),
            "instance should be deleted when buffer reaches 0",
        )

        # Second hit: no buffer → full damage
        result2 = apply_damage_to_participant(
            self.participant, 20, damage_type=None, source=self.enemy
        )
        self.assertGreater(
            result2.damage_dealt,
            0,
            "second hit after buffer depletion should land (no force-field active)",
        )
