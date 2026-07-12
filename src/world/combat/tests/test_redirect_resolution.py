"""Tests for guardian redirect declaration + resolution (#2210).

Mirrors ``test_guardian_reactions.py``'s ``TechniqueGuardianBarrierResolutionTest``
setup shape: a guardian who knows Mirror Ward (the seeded REDIRECT-flavor
protective technique, ``world.magic.effect_palette_content.ensure_reflect_content``)
declares Interpose "with" it, damage lands on the ward, and the REAL dispatch
path (``apply_damage_to_participant`` -> ``_try_interpose`` -> (technique set)
-> ``_try_technique_interpose``) resolves the REDIRECT branch.

Untagged (SQLite fast tier): the technique branch never calls
``apply_condition``/``get_available_actions`` (no DISTINCT ON dependency).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from evennia import create_object

from world.areas.positioning.factories import PositionFactory
from world.areas.positioning.services import place_in_position
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import CombatManeuver, OpponentStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundAction,
)
from world.combat.interpose_content import ensure_interpose_content
from world.combat.redirect_content import ensure_redirect_content
from world.combat.services import apply_damage_to_participant, declare_interpose
from world.magic.effect_palette_content import REFLECT_TECHNIQUE_NAME, ensure_reflect_content
from world.magic.factories import CharacterAnimaFactory
from world.magic.models import CharacterTechnique, Technique
from world.mechanics.models import ObjectProperty
from world.scenes.constants import RoundStatus
from world.vitals.models import CharacterVitals


def _make_vitals(participant, health: int = 100, max_health: int = 100) -> CharacterVitals:
    vitals, _ = CharacterVitals.objects.get_or_create(
        character_sheet=participant.character_sheet,
        defaults={"health": health, "max_health": max_health},
    )
    vitals.health = health
    vitals.max_health = max_health
    vitals.save()
    return vitals


def _fake_perform_check(success_level: int):
    def _inner(character, check_type, *args, **kwargs):
        return SimpleNamespace(success_level=success_level)

    return _inner


class RedirectDeclarationTest(TestCase):
    """declare_interpose accepts a REDIRECT-flavor technique + validates destinations."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        ensure_reflect_content()
        self.mirror_ward = Technique.objects.get(name=REFLECT_TECHNIQUE_NAME)

        self.room = create_object("typeclasses.rooms.Room", key="RedirectDeclareRoom", nohome=True)
        self.encounter = CombatEncounterFactory(status=RoundStatus.DECLARING, room=self.room)

        self.guardian_sheet = CharacterSheetFactory()
        self.guardian_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.guardian_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CharacterTechnique.objects.create(character=self.guardian_sheet, technique=self.mirror_ward)

    def test_redirect_technique_now_accepted(self) -> None:
        action = declare_interpose(self.guardian_participant, technique=self.mirror_ward)
        self.assertEqual(action.focused_action_id, self.mirror_ward.pk)
        self.assertIsNone(action.redirect_opponent_target_id)
        self.assertIsNone(action.redirect_object_target_id)

    def test_wrong_encounter_enemy_rejected(self) -> None:
        other_encounter = CombatEncounterFactory(status=RoundStatus.DECLARING)
        other_opponent = CombatOpponentFactory(
            encounter=other_encounter, status=OpponentStatus.ACTIVE
        )
        with self.assertRaises(ValueError):
            declare_interpose(
                self.guardian_participant,
                technique=self.mirror_ward,
                redirect_opponent_target=other_opponent,
            )

    def test_non_volatile_object_rejected(self) -> None:
        plain = create_object("typeclasses.objects.Object", key="PlainCrate", location=self.room)
        with self.assertRaises(ValueError):
            declare_interpose(
                self.guardian_participant,
                technique=self.mirror_ward,
                redirect_object_target=plain,
            )

    def test_volatile_object_accepted(self) -> None:
        volatile_property = ensure_redirect_content()
        keg = create_object("typeclasses.objects.Object", key="PowderKeg", location=self.room)
        ObjectProperty.objects.create(object=keg, property=volatile_property)

        action = declare_interpose(
            self.guardian_participant,
            technique=self.mirror_ward,
            redirect_object_target=keg,
        )
        self.assertEqual(action.redirect_object_target_id, keg.pk)


class _RedirectResolutionTestBase(TestCase):
    """Shared setup: a guardian knows Mirror Ward, wards a specific ally."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        ensure_interpose_content()
        ensure_reflect_content()
        self.mirror_ward = Technique.objects.get(name=REFLECT_TECHNIQUE_NAME)

        self.room = create_object("typeclasses.rooms.Room", key="RedirectResolveRoom", nohome=True)
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.RESOLVING, round_number=1, room=self.room
        )

        self.guardian_sheet = CharacterSheetFactory()
        self.guardian_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.guardian_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.guardian = self.guardian_sheet.character
        self.guardian.db_location = self.room
        self.guardian.save(update_fields=["db_location"])

        self.ally_sheet = CharacterSheetFactory()
        self.ally_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.ally = self.ally_sheet.character
        self.ally.db_location = self.room
        self.ally.save(update_fields=["db_location"])

        CharacterTechnique.objects.create(character=self.guardian_sheet, technique=self.mirror_ward)
        self.starting_anima = 10
        self.anima = CharacterAnimaFactory(
            character=self.guardian, current=self.starting_anima, maximum=10
        )
        self.ally_vitals = _make_vitals(self.ally_participant, health=100, max_health=100)
        _make_vitals(self.guardian_participant)

    def _declare(self, **redirect_kwargs) -> CombatRoundAction:
        return CombatRoundAction.objects.create(
            participant=self.guardian_participant,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target=self.ally_participant,
            focused_action=self.mirror_ward,
            is_ready=True,
            **redirect_kwargs,
        )


class RedirectAwayResolutionTest(_RedirectResolutionTestBase):
    """No declared destination (the default) — the universal 'away' fallback."""

    def test_away_zeroes_damage_and_broadcasts(self) -> None:
        self._declare()

        with patch("world.combat.services.perform_check", side_effect=_fake_perform_check(2)):
            apply_damage_to_participant(self.ally_participant, 40)

        self.ally_vitals.refresh_from_db()
        self.assertEqual(
            self.ally_vitals.health,
            100,
            "a clean block must still zero the damage reaching the ward",
        )


class RedirectChosenEnemyResolutionTest(_RedirectResolutionTestBase):
    """The declared opponent takes the saved amount; a defeated one degrades to away."""

    def setUp(self) -> None:
        super().setUp()
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            status=OpponentStatus.ACTIVE,
            health=100,
            max_health=100,
        )

    def test_clean_grade_sends_full_saved_amount(self) -> None:
        self._declare(redirect_opponent_target=self.opponent)

        with patch("world.combat.services.perform_check", side_effect=_fake_perform_check(2)):
            apply_damage_to_participant(self.ally_participant, 40)

        self.ally_vitals.refresh_from_db()
        self.opponent.refresh_from_db()
        self.assertEqual(self.ally_vitals.health, 100, "the ward takes no damage")
        self.assertEqual(
            self.opponent.health,
            60,
            "a clean block sends the FULL prevented amount (40) to the enemy",
        )

    def test_partial_grade_sends_half_saved_amount(self) -> None:
        self._declare(redirect_opponent_target=self.opponent)

        # success_level == 0 -> partial block, halving the prevented amount.
        with patch("world.combat.services.perform_check", side_effect=_fake_perform_check(0)):
            apply_damage_to_participant(self.ally_participant, 40)

        self.ally_vitals.refresh_from_db()
        self.opponent.refresh_from_db()
        self.assertEqual(self.ally_vitals.health, 80, "a partial block halves the ward's damage")
        self.assertEqual(
            self.opponent.health,
            80,
            "a partial block sends only the prevented HALF (20) to the enemy",
        )

    def test_defeated_target_degrades_to_away(self) -> None:
        self.opponent.status = OpponentStatus.DEFEATED
        self.opponent.save(update_fields=["status"])
        self._declare(redirect_opponent_target=self.opponent)

        with patch("world.combat.services.perform_check", side_effect=_fake_perform_check(2)):
            apply_damage_to_participant(self.ally_participant, 40)

        self.ally_vitals.refresh_from_db()
        self.opponent.refresh_from_db()
        self.assertEqual(self.ally_vitals.health, 100, "the ward is still shielded")
        self.assertEqual(
            self.opponent.health, 100, "a defeated declared target must not take the redirect"
        )


class RedirectVolatileObjectResolutionTest(_RedirectResolutionTestBase):
    """The declared volatile object detonates once, then degrades to away."""

    def setUp(self) -> None:
        super().setUp()
        self.volatile_property = ensure_redirect_content()
        self.keg = create_object("typeclasses.objects.Object", key="PowderKeg", location=self.room)
        self.object_property = ObjectProperty.objects.create(
            object=self.keg, property=self.volatile_property
        )
        self.position = PositionFactory(room=self.room)
        place_in_position(self.keg, self.position)
        place_in_position(self.ally, self.position)

    def test_detonation_fires_pool_and_consumes_property(self) -> None:
        self._declare(redirect_object_target=self.keg)

        with (
            patch("world.combat.services.perform_check", side_effect=_fake_perform_check(2)),
            patch("world.room_features.trap_services.fire_pool_at_characters") as mock_fire,
        ):
            apply_damage_to_participant(self.ally_participant, 40)

        self.assertEqual(mock_fire.call_count, 1)
        pool_arg = mock_fire.call_args.args[0]
        self.assertEqual(pool_arg, self.volatile_property.detonation.consequence_pool)
        fired_characters = mock_fire.call_args.args[1]
        self.assertIn(self.ally, list(fired_characters))
        self.assertFalse(
            ObjectProperty.objects.filter(pk=self.object_property.pk).exists(),
            "the volatile ObjectProperty must be consumed (deleted) — one-shot",
        )

    def test_already_consumed_object_degrades_to_away(self) -> None:
        self.object_property.delete()
        self._declare(redirect_object_target=self.keg)

        with patch("world.combat.services.perform_check", side_effect=_fake_perform_check(2)):
            apply_damage_to_participant(self.ally_participant, 40)

        self.ally_vitals.refresh_from_db()
        self.assertEqual(
            self.ally_vitals.health, 100, "the ward is still shielded even on degrade-to-away"
        )
