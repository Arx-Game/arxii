"""End-to-end: Succor (#1744) shelters a vampire PC from Sunlight Exposure DoT in combat.

Full player journey: an ally declares "combat succor <vampire>" through the real
dispatch seam (``dispatch_player_action`` — the exact path ``CmdCombat``/the web
viewset use) against a vampire PC outdoors at noon with an active radiant DoT
(Sunlight Exposure) in a live ``CombatEncounter``; the round-tick DoT-application
path (``_apply_round_tick_damage``) consults the ally's graded Succor cover and
reduces/blocks the DoT that would otherwise apply. Mirrors
``test_interpose_damage_path.py``'s ``InterposeReducesAllyDamageTest`` setup style
(real CG-pipeline character fixtures, real capability grant, mocked
``perform_check`` for a deterministic graded outcome) and
``test_sunlight_exposure_e2e.py``'s vampire/outdoor/noon fixture pattern.

NOTE — real-lifecycle timing gap discovered while writing this test, since closed:
``CombatRoundContext.get_cover_for`` only grants cover while
``encounter.status == RESOLVING``. Sunlight Exposure's ``ConditionDamageOverTime``
originally ticked at ``DamageTickTiming.START_OF_ROUND`` (the model default), but
combat's real START tick (``begin_declaration_phase``) fires while status is still
``DECLARING`` — before that round's Succor could even be declared — so Succor could
never cover a START-tagged hazard. Sunlight Exposure now ticks
``DamageTickTiming.END_OF_ROUND`` instead (matching poison's convention), and
``resolve_round`` sets ``encounter.status = RESOLVING`` before firing the END tick,
so the real ``begin_declaration_phase``/``resolve_round`` lifecycle can now reach
this DoT. This test still calls ``tick_round_for_targets(..., timing="end")``
directly rather than running the full ``resolve_round`` machinery, and ``setUp``
forces ``encounter.status = RESOLVING`` up front to exercise the
``get_cover_for``/``_apply_round_tick_damage`` integration in isolation — a
simplification, not a workaround for an unreachable path.

Tagged postgres: both Sunlight Exposure's ``apply_condition`` and the ally's
telekinesis capability grant (also ``apply_condition``) hit the PG-only
``DISTINCT ON`` path in ``get_available_actions`` — the same pre-existing
limitation as ``InterposeReducesAllyDamageTest`` and
``SunlightExposureE2ETests``; runs on CI's PG shard.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, tag

from actions.constants import ActionBackend
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from world.combat.constants import ActionCategory, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatRoundAction
from world.combat.succor_content import ensure_succor_content
from world.mechanics.succor_shared import SUCCOR_CHALLENGE_NAME
from world.scenes.constants import RoundStatus
from world.species.factories import ensure_sunlight_exposure_content
from world.vitals.models import CharacterVitals
from world.vitals.services import tick_round_for_targets


def _ref(registry_key: str) -> ActionRef:
    return ActionRef(backend=ActionBackend.REGISTRY, registry_key=registry_key)


def _make_vitals(participant, health: int = 100, max_health: int = 100) -> CharacterVitals:
    vitals, _ = CharacterVitals.objects.get_or_create(
        character_sheet=participant.character_sheet,
        defaults={"health": health, "max_health": max_health},
    )
    vitals.health = health
    vitals.max_health = max_health
    vitals.save()
    return vitals


@tag("postgres")  # apply_condition (Sunlight Exposure + capability grant) uses DISTINCT ON
class SuccorCombatE2ETests(TestCase):
    def setUp(self) -> None:
        from evennia import create_object
        from evennia.utils.idmapper import models as idmapper_models

        from evennia_extensions.models import RoomProfile
        from world.character_sheets.factories import CharacterSheetFactory
        from world.conditions.factories import (
            ConditionCapabilityEffectFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import CapabilityType
        from world.conditions.services import apply_condition
        from world.game_clock.constants import TimePhase
        from world.magic.factories import GiftFactory
        from world.mechanics.models import ChallengeInstance, ChallengeTemplate
        from world.species.factories import SpeciesFactory, SpeciesGiftGrantFactory
        from world.traits.factories import CheckSystemSetupFactory
        from world.traits.models import ResultChart

        idmapper_models.flush_cache()

        ensure_succor_content()
        self.sunlight_template = ensure_sunlight_exposure_content()

        # Seed the check-resolution pipeline so the Succor approach isn't dropped as
        # IMPOSSIBLE (mirrors InterposeReducesAllyDamageTest.setUp).
        CheckSystemSetupFactory.create()
        ResultChart.clear_cache()

        self.room = create_object("typeclasses.rooms.Room", key="SunnyBattlefield", nohome=True)
        RoomProfile.objects.update_or_create(objectdb=self.room, defaults={"is_outdoor": True})

        self.encounter = CombatEncounterFactory(
            status=RoundStatus.DECLARING, round_number=1, room=self.room
        )

        species = SpeciesFactory(name="Vampire")
        gift = GiftFactory()
        SpeciesGiftGrantFactory(
            species=species, gift=gift, drawback_condition=self.sunlight_template
        )

        vampire_sheet = CharacterSheetFactory(species=species)
        self.vampire_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=vampire_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.vampire = vampire_sheet.character
        self.vampire.db_location = self.room
        self.vampire.save(update_fields=["db_location"])
        self.vampire_vitals = _make_vitals(self.vampire_participant, health=100, max_health=100)

        ally_sheet = CharacterSheetFactory()
        self.ally_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        self.ally = ally_sheet.character
        self.ally.db_location = self.room
        self.ally.save(update_fields=["db_location"])
        _make_vitals(self.ally_participant)

        # Outdoors + noon -> the vampire's Sunlight Exposure drawback is active.
        with patch("world.species.services.get_ic_phase", return_value=TimePhase.DAY):
            apply_condition(self.vampire, self.sunlight_template)

        # The ally can shelter allies via telekinesis (a seeded Succor capability).
        telekinesis = CapabilityType.objects.get(name="telekinesis")
        grant_template = ConditionTemplateFactory(name="TelekineticSuccorer")
        ConditionCapabilityEffectFactory(condition=grant_template, capability=telekinesis, value=10)
        apply_condition(self.ally, grant_template)

        # Real player-facing path: "combat succor <vampire>" via the shared
        # dispatch seam — CmdCombat and the web CombatEncounterViewSet converge here.
        result = dispatch_player_action(
            self.ally,
            _ref("combat_succor"),
            {"ally_participant_id": self.vampire_participant.pk},
        )
        assert result.detail is not None
        assert result.detail.success, result.detail.message

        # Bind the Succor ChallengeInstance to the vampire — resolve_round's own
        # pre-pass (_ensure_reactive_challenges) does this too; done here directly
        # because this test drives the round tick without running the full
        # resolve_round (mirrors InterposeReducesAllyDamageTest's own pre-bind).
        template = ChallengeTemplate.objects.get(name=SUCCOR_CHALLENGE_NAME)
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=self.vampire,
            is_active=True,
            defaults={"location": self.room, "is_revealed": True},
        )

        # The Succor cover is only consulted while the encounter is RESOLVING
        # (CombatRoundContext.get_cover_for's status gate) — see the module
        # docstring's NOTE for why this is forced rather than reached naturally.
        self.encounter.status = RoundStatus.RESOLVING
        self.encounter.save(update_fields=["status"])

    def _round_action(self) -> CombatRoundAction:
        return CombatRoundAction.objects.get(
            participant=self.ally_participant, round_number=self.encounter.round_number
        )

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_succor_blocks_sunlight_exposure_round_tick_damage(self, mock_check) -> None:
        """A clean-block graded outcome leaves the vampire's round-tick DoT fully covered."""
        from world.checks.types import CheckResult
        from world.traits.factories import CheckOutcomeFactory

        clean = CheckOutcomeFactory(name="CleanShelter", success_level=2)
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

        health_before = self.vampire_vitals.health
        tick_round_for_targets([self.vampire], timing="end")

        self.assertTrue(mock_check.called, "dispatch_succor must route through perform_check")
        self.vampire_vitals.refresh_from_db()
        self.assertEqual(
            self.vampire_vitals.health,
            health_before,
            "a clean Succor block must leave the vampire's Sunlight Exposure DoT fully covered",
        )
        action = self._round_action()
        self.assertEqual(action.succor_resolution, 0.0)

    @patch("world.mechanics.challenge_resolution.perform_check")
    def test_succor_fatigue_charged_exactly_once_across_repeated_ticks(self, mock_check) -> None:
        """Fatigue is charged once per round even when the round-tick DoT-application path
        is consulted more than once this round — the cached
        ``CombatRoundAction.succor_resolution`` short-circuits any further
        ``apply_fatigue`` call (#1744 Decision 8).

        Scoped down from a true multi-hazard scenario (a second real hazard condition
        landing the same round, which would need its own DoT-bearing condition
        fixture) to a repeated-tick simulation against the single Sunlight Exposure
        DoT already in play — this still proves the caching invariant end-to-end
        (vitals + fatigue + a single ``perform_check`` roll), just without a second
        independently-seeded hazard source.
        """
        from world.checks.types import CheckResult
        from world.fatigue.services import get_or_create_fatigue_pool
        from world.traits.factories import CheckOutcomeFactory

        clean = CheckOutcomeFactory(name="CleanShelter2", success_level=2)
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

        pool = get_or_create_fatigue_pool(self.ally_participant.character_sheet)
        fatigue_before = pool.get_current(ActionCategory.PHYSICAL)

        tick_round_for_targets([self.vampire], timing="end")
        pool.refresh_from_db()
        fatigue_after_first = pool.get_current(ActionCategory.PHYSICAL)
        self.assertGreater(
            fatigue_after_first,
            fatigue_before,
            "the ally's first Succor resolution this round must charge fatigue",
        )

        # A second tick this same round (simulating an additional DoT row / a
        # re-entrant call) must NOT re-charge fatigue — the resolution is cached.
        tick_round_for_targets([self.vampire], timing="end")
        pool.refresh_from_db()
        fatigue_after_second = pool.get_current(ActionCategory.PHYSICAL)
        self.assertEqual(
            fatigue_after_second,
            fatigue_after_first,
            "a second tick this round must reuse the cached succor_resolution, "
            "not re-charge fatigue",
        )
        self.assertEqual(
            mock_check.call_count, 1, "perform_check must not re-roll on the second tick"
        )
