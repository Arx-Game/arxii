"""End-to-end: Succor (#1744) shelters a vampire PC from Sunlight Exposure DoT in a
non-combat danger scene round.

Full player journey: outdoors at noon, NOT in combat, a danger ``SceneRound`` is
active via ``ensure_round_for_acute_condition`` (the #1588 plummet pattern); an ally
dispatches "scene succor <vampire>" through the real dispatch seam
(``dispatch_player_action`` — the exact path ``CmdScene``/the web viewset use); the
round-tick DoT-application path (``_apply_round_tick_damage``) consults the ally's
graded Succor cover and reduces/blocks the DoT that would otherwise apply. Mirrors
``test_sunlight_exposure_e2e.py``'s vampire/outdoor/noon fixture pattern and
``test_succor_e2e.py``'s (combat) capability-grant + mocked ``perform_check``
pattern.

NOTE — real-lifecycle gap discovered while writing this test (the scene-round
sibling of the one documented in ``test_succor_e2e.py``), since closed:
``resolve_scene_round`` only ever fires the shared round-tick at ``timing="end"``
(``DamageTickTiming.END_OF_ROUND``); nothing in the scene-round lifecycle ever
calls a ``timing="start"`` tick. Sunlight Exposure originally ticked at
``DamageTickTiming.START_OF_ROUND`` (the model default), so it never dealt damage
through the real ``resolve_scene_round`` production path regardless of Succor.
Sunlight Exposure now ticks ``DamageTickTiming.END_OF_ROUND`` instead (matching
poison's convention), so it's reachable through the real production path — see
``test_sunlight_exposure_e2e.py``'s ``test_ticks_through_real_scene_round_production_path``.
This test still calls ``tick_round_for_targets(..., timing="end")`` directly
rather than ``resolve_scene_round`` so it isolates the DoT-application/Succor-cover
integration from the rest of round resolution. ``SceneRoundContext.get_cover_for``
(unlike combat's) has no round-status gate, so this still exercises the real
Succor-cover resolution chain (``dispatch_capability_reaction`` ->
``apply_succor_outcome`` -> cached ``SceneActionDeclaration.succor_resolution``)
untouched.

Tagged postgres: both Sunlight Exposure's ``apply_condition`` and the ally's
telekinesis capability grant (also ``apply_condition``) hit the PG-only
``DISTINCT ON`` path in ``get_available_actions`` — same pre-existing limitation as
``SunlightExposureE2ETests``; runs on CI's PG shard.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, tag

from actions.constants import ActionBackend
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from world.mechanics.succor_shared import SUCCOR_CHALLENGE_NAME
from world.scenes.models import SceneActionDeclaration, SceneRoundParticipant
from world.species.factories import ensure_sunlight_exposure_content
from world.vitals.models import CharacterVitals


def _ref(registry_key: str) -> ActionRef:
    return ActionRef(backend=ActionBackend.REGISTRY, registry_key=registry_key)


@tag("postgres")  # apply_condition (Sunlight Exposure + capability grant) uses DISTINCT ON
class SuccorSceneE2ETests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object
        from evennia.utils.idmapper import models as idmapper_models

        from evennia_extensions.models import RoomProfile
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.succor_content import ensure_succor_content
        from world.conditions.factories import (
            ConditionCapabilityEffectFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import CapabilityType
        from world.conditions.services import apply_condition
        from world.game_clock.constants import TimePhase
        from world.magic.factories import GiftFactory
        from world.mechanics.models import ChallengeInstance, ChallengeTemplate
        from world.scenes.round_services import ensure_round_for_acute_condition
        from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory
        from world.traits.factories import CheckSystemSetupFactory
        from world.traits.models import ResultChart

        idmapper_models.flush_cache()

        ensure_succor_content()
        self.sunlight_template = ensure_sunlight_exposure_content()

        # Seed the check-resolution pipeline so the Succor approach isn't dropped
        # as IMPOSSIBLE (mirrors test_succor_e2e.py's combat E2E setup).
        CheckSystemSetupFactory.create()
        ResultChart.clear_cache()

        self.room = create_object("typeclasses.rooms.Room", key="SunnyCourtyard", nohome=True)
        RoomProfile.objects.update_or_create(objectdb=self.room, defaults={"is_outdoor": True})

        species = SpeciesFactory(name="Vampire")
        gift = GiftFactory()
        SpeciesGiftGrantFactory(
            species=species, gift=gift, drawback_condition=self.sunlight_template
        )

        vampire_sheet = CharacterSheetFactory(species=species)
        self.vampire = self._place_character(vampire_sheet)
        self.vampire_sheet = vampire_sheet

        ally_sheet = CharacterSheetFactory()
        self.ally = self._place_character(ally_sheet)

        # Outdoors + noon -> the vampire's Sunlight Exposure drawback is active.
        with patch("world.species.services.get_ic_phase", return_value=TimePhase.DAY):
            apply_condition(self.vampire, self.sunlight_template)

        # The ally can shelter allies via telekinesis (a seeded Succor capability).
        telekinesis = CapabilityType.objects.get(name="telekinesis")
        grant_template = ConditionTemplateFactory(name="TelekineticSceneSuccorer")
        ConditionCapabilityEffectFactory(condition=grant_template, capability=telekinesis, value=10)
        apply_condition(self.ally, grant_template)

        # NOT in combat: a danger SceneRound is ensured for the room (the #1588
        # plummet pattern) — enrolls everyone present, including the ally.
        self.scene_round = ensure_round_for_acute_condition(self.vampire_sheet)
        assert self.scene_round is not None

        self.vampire_participant = SceneRoundParticipant.objects.get(
            scene_round=self.scene_round, character_sheet=vampire_sheet
        )
        self.ally_participant = SceneRoundParticipant.objects.get(
            scene_round=self.scene_round, character_sheet=ally_sheet
        )

        # Real player-facing path: "scene succor <vampire>" via the shared dispatch
        # seam — CmdScene and the web viewset converge here too.
        result = dispatch_player_action(
            self.ally, _ref("scene_succor"), {"ally_name": self.vampire.db_key}
        )
        assert result.detail is not None
        assert result.detail.success, result.detail.message

        # Bind the Succor ChallengeInstance to the vampire — resolve_scene_round's
        # own pre-pass (ensure_succor_challenges_for_round) would do this too; bound
        # here directly since this test drives the tick without resolve_scene_round
        # (see the module NOTE for why).
        template = ChallengeTemplate.objects.get(name=SUCCOR_CHALLENGE_NAME)
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=self.vampire,
            is_active=True,
            defaults={"location": self.room, "is_revealed": True},
        )

    def _place_character(self, sheet):
        """Give *sheet* full vitals and place its character in ``self.room``."""
        from world.vitals.factories import CharacterVitalsFactory

        CharacterVitalsFactory(character_sheet=sheet, health=100, max_health=100)
        character = sheet.character
        character.db_location = self.room
        character.save(update_fields=["db_location"])
        return character

    def _vitals(self) -> CharacterVitals:
        return self.vampire_sheet.vitals

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_succor_blocks_sunlight_exposure_round_tick_damage(self, mock_check) -> None:
        """A clean-block graded outcome leaves the vampire's round-tick DoT fully covered."""
        from world.checks.types import CheckResult
        from world.traits.factories import CheckOutcomeFactory
        from world.vitals.services import tick_round_for_targets

        clean = CheckOutcomeFactory(name="CleanSceneShelter", success_level=2)
        mock_check.return_value = CheckResult(
            check_type=None,
            outcome=clean,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

        health_before = self._vitals().health
        tick_round_for_targets([self.vampire], timing="end")

        self.assertTrue(mock_check.called, "dispatch_succor must route through perform_check")
        self._vitals().refresh_from_db()
        self.assertEqual(
            self._vitals().health,
            health_before,
            "a clean Succor block must leave the vampire's Sunlight Exposure DoT fully covered",
        )

        declaration = SceneActionDeclaration.objects.get(
            scene_round=self.scene_round,
            round_number=self.scene_round.round_number,
            succor_target=self.vampire_participant,
        )
        self.assertEqual(declaration.succor_resolution, 0.0)
