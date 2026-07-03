"""Tests for knockback + Trap position-scoping wired into combat (#1317).

Knockback is authored as an on-hit ConsequencePool on ThreatPoolEntry, fired
deterministically (no roll — the attack's own hit already determined it
landed) after the existing #1273 Interpose seam resolves, using the same
mutable DamagePreApplyPayload.amount check that makes "clean interpose also
blocks the knockback" fall out for free.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.factories import ConsequencePoolEntryFactory, ConsequencePoolFactory
from evennia_extensions.factories import RoomProfileFactory
from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import connect_positions, place_in_position, position_of
from world.checks.constants import EffectTarget, EffectType, PositionDestination
from world.checks.factories import CheckTypeFactory, ConsequenceEffectFactory, ConsequenceFactory
from world.checks.test_helpers import force_check_outcome
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    ThreatPoolEntryFactory,
    ThreatPoolFactory,
)
from world.combat.models import CombatOpponentAction
from world.combat.services import (
    apply_damage_to_participant,
    resolve_npc_attack,
    resolve_round,
    select_npc_actions,
)
from world.conditions.factories import DamageTypeFactory
from world.room_features.factories import TrapFactory
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals


class ThreatPoolEntryOnHitPoolTest(TestCase):
    def test_on_hit_consequence_pool_defaults_to_none(self) -> None:
        entry = ThreatPoolEntryFactory()
        assert entry.on_hit_consequence_pool is None


def _make_vitals(participant, health: int = 100, max_health: int = 100) -> CharacterVitals:
    vitals, _ = CharacterVitals.objects.get_or_create(
        character_sheet=participant.character_sheet,
        defaults={"health": health, "max_health": max_health},
    )
    vitals.health = health
    vitals.max_health = max_health
    vitals.save()
    return vitals


class OnHitPoolKnockbackTest(TestCase):
    """apply_damage_to_participant fires on_hit_pool after Interpose resolves."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.vitals = _make_vitals(self.participant, health=100, max_health=100)
        self.defender = self.participant.character_sheet.character
        self.room = self.encounter.room
        self.defender.db_location = self.room
        self.defender.save(update_fields=["db_location"])

        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.attacker_pos = PositionFactory(room=self.room, name="attacker_spot")
        self.defender_pos = PositionFactory(room=self.room, name="defender_spot")
        self.far_pos = PositionFactory(room=self.room, name="far_spot")
        connect_positions(self.attacker_pos, self.defender_pos)
        connect_positions(self.defender_pos, self.far_pos)
        place_in_position(self.opponent.objectdb, self.attacker_pos)
        place_in_position(self.defender, self.defender_pos)

        pool = ConsequencePoolFactory()
        consequence = ConsequenceFactory()
        ConsequenceEffectFactory(
            consequence=consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.AWAY_FROM_ACTOR,
            target=EffectTarget.TARGET,
        )
        ConsequencePoolEntryFactory(pool=pool, consequence=consequence)
        self.pool = pool

    def _health(self) -> int:
        self.vitals.refresh_from_db()
        return self.vitals.health

    def test_on_hit_pool_knocks_defender_back(self) -> None:
        with patch("world.combat.services._try_interpose"):
            apply_damage_to_participant(
                self.participant, 10, source=self.opponent, on_hit_pool=self.pool
            )

        self.assertEqual(position_of(self.defender).pk, self.far_pos.pk)

    def test_clean_interpose_blocks_knockback(self) -> None:
        """A clean interpose block zeroes pre_payload.amount before the on-hit
        pool check runs -- so the knockback never fires (#1273 seam reuse)."""

        def _zero_payload(participant, pre_payload):
            pre_payload.amount = 0

        with patch("world.combat.services._try_interpose", side_effect=_zero_payload):
            apply_damage_to_participant(
                self.participant, 10, source=self.opponent, on_hit_pool=self.pool
            )

        self.assertEqual(position_of(self.defender).pk, self.defender_pos.pk)

    def test_on_hit_pool_none_is_a_noop(self) -> None:
        """No on_hit_pool -> no knockback, existing callers unaffected."""
        with patch("world.combat.services._try_interpose"):
            apply_damage_to_participant(self.participant, 10, source=self.opponent)

        self.assertEqual(position_of(self.defender).pk, self.defender_pos.pk)


class OnHitPoolKnockbackIntoTrapTest(TestCase):
    """Knockback landing on a position-scoped Trap resolves its consequence pool."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        self.failure_outcome = CheckOutcomeFactory(name="Spike-Failure", success_level=0)

        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.vitals = _make_vitals(self.participant, health=100, max_health=100)
        self.defender = self.participant.character_sheet.character
        self.room = self.encounter.room
        self.defender.db_location = self.room
        self.defender.save(update_fields=["db_location"])

        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.attacker_pos = PositionFactory(room=self.room, name="attacker_spot")
        self.defender_pos = PositionFactory(room=self.room, name="defender_spot")
        self.spike_pos = PositionFactory(room=self.room, name="spike_pit")
        connect_positions(self.attacker_pos, self.defender_pos)
        connect_positions(self.defender_pos, self.spike_pos)
        place_in_position(self.opponent.objectdb, self.attacker_pos)
        place_in_position(self.defender, self.defender_pos)

        trap_pool = ConsequencePoolFactory()
        trap_consequence = ConsequenceFactory(
            outcome_tier=self.failure_outcome, character_loss=False
        )
        ConsequenceEffectFactory(
            consequence=trap_consequence,
            effect_type=EffectType.DEAL_DAMAGE,
            target=EffectTarget.SELF,
            damage_amount=30,
            damage_type=DamageTypeFactory(name="spike-trap"),
        )
        ConsequencePoolEntryFactory(pool=trap_pool, consequence=trap_consequence)
        self.trap = TrapFactory(
            room_profile=RoomProfileFactory(objectdb=self.room),
            position=self.spike_pos,
            consequence_pool=trap_pool,
        )

        knockback_pool = ConsequencePoolFactory()
        knockback_consequence = ConsequenceFactory()
        ConsequenceEffectFactory(
            consequence=knockback_consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.AWAY_FROM_ACTOR,
            target=EffectTarget.TARGET,
        )
        ConsequencePoolEntryFactory(pool=knockback_pool, consequence=knockback_consequence)
        self.knockback_pool = knockback_pool

    def _health(self) -> int:
        self.vitals.refresh_from_db()
        return self.vitals.health

    def test_knockback_into_trap_position_fires_trap(self) -> None:
        with patch("world.combat.services._try_interpose"):
            with force_check_outcome(self.failure_outcome):
                apply_damage_to_participant(
                    self.participant, 10, source=self.opponent, on_hit_pool=self.knockback_pool
                )

        self.assertEqual(position_of(self.defender).pk, self.spike_pos.pk)
        self.assertEqual(self._health(), 60)  # 100 - 10 (hit) - 30 (trap)


class ResolveNpcAttackPassesOnHitPoolTest(TestCase):
    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        self.encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1)
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        _make_vitals(self.participant, health=100, max_health=100)
        character = self.participant.character_sheet.character
        character.db_location = self.encounter.room
        character.save(update_fields=["db_location"])

        pool = ConsequencePoolFactory()
        self.threat_entry = ThreatPoolEntryFactory(base_damage=10, on_hit_consequence_pool=pool)
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        self.opponent_action = CombatOpponentAction.objects.create(
            opponent=self.opponent,
            threat_entry=self.threat_entry,
            round_number=1,
        )
        self.check_type = CheckTypeFactory(name="Defense")

    def test_resolve_npc_attack_passes_on_hit_pool_through(self) -> None:
        with patch("world.combat.services.apply_damage_to_participant") as mock_apply:
            mock_apply.return_value = None
            resolve_npc_attack(self.opponent_action, self.participant, self.check_type)

        _, kwargs = mock_apply.call_args
        self.assertEqual(kwargs["on_hit_pool"], self.threat_entry.on_hit_consequence_pool)


class KnockbackViaResolveRoundTest(TestCase):
    """E2E: drives the real production entry point, ``resolve_round(encounter)``,
    with NO ``defense_check_type`` passed -- exactly how every production caller
    (views.py, tasks.py, gm_combat.py) invokes it. This is the actual bug from
    #1317's whole-branch review: when ``defense_check_type`` is None,
    ``_resolve_npc_action_on_target`` takes the flat-damage ``else`` branch,
    which previously dropped ``on_hit_pool`` on the floor -- so an authored
    knockback never fired in real gameplay even though the defense-check branch
    (``resolve_npc_attack``) wired it correctly. This test proves the fix: a
    plain ``resolve_round(encounter)`` call now actually shoves the defending
    PC to the expected Position.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, round_number=1)
        self.room = self.encounter.room

        pool = ThreatPoolFactory()
        knockback_pool = ConsequencePoolFactory()
        knockback_consequence = ConsequenceFactory()
        ConsequenceEffectFactory(
            consequence=knockback_consequence,
            effect_type=EffectType.MOVE_TO_POSITION,
            position_destination=PositionDestination.AWAY_FROM_ACTOR,
            target=EffectTarget.TARGET,
        )
        ConsequencePoolEntryFactory(pool=knockback_pool, consequence=knockback_consequence)
        self.threat_entry = ThreatPoolEntryFactory(
            pool=pool, base_damage=10, on_hit_consequence_pool=knockback_pool
        )

        self.opponent = CombatOpponentFactory(encounter=self.encounter, threat_pool=pool)

        self.participant = CombatParticipantFactory(encounter=self.encounter)
        _make_vitals(self.participant, health=100, max_health=100)
        self.defender = self.participant.character_sheet.character
        self.defender.db_location = self.room
        self.defender.save(update_fields=["db_location"])

        self.attacker_pos = PositionFactory(room=self.room, name="attacker_spot")
        self.defender_pos = PositionFactory(room=self.room, name="defender_spot")
        self.far_pos = PositionFactory(room=self.room, name="far_spot")
        connect_positions(self.attacker_pos, self.defender_pos)
        connect_positions(self.defender_pos, self.far_pos)
        place_in_position(self.opponent.objectdb, self.attacker_pos)
        place_in_position(self.defender, self.defender_pos)

    def test_resolve_round_with_no_defense_check_type_still_fires_knockback(self) -> None:
        emitted = select_npc_actions(self.encounter)
        self.assertEqual(len(emitted), 1)

        # The real production call: no defense_check_type passed, so the
        # flat-damage `else` branch in _resolve_npc_action_on_target runs.
        resolve_round(self.encounter)

        self.assertEqual(position_of(self.defender).pk, self.far_pos.pk)
