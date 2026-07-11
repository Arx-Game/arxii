"""Test for the interpose best-of-check selection on the REAL dispatch path (#2207).

Task 1 originally shipped a Melee-Defense twin keyed on a separate, ungranted
``melee_guard`` CapabilityType and a unit test that called the (now-removed)
``_better_interpose_approach`` helper directly — which meant the twin was
provably unreachable for any real guardian: ``_match_approaches``
(``world/mechanics/services.py``) keys strictly on ``capability_id``, and
``_select_reaction_action`` (``world/mechanics/reactions.py``) name-matches
``capability_source.capability_name``, which condition sources always set to
``""``.

The fix re-keys the twin ``Application`` to reuse each base interpose
capability's own ``CapabilityType`` (so a condition-granted guardian's
``reaction_actions`` naturally contains BOTH the Reflexes and Melee-Defense
flavors) and moves the best-of pick into
``world.mechanics.reactions.dispatch_capability_reaction``'s opt-in
``select_best_check_rating`` mode, which rates each DISTINCT ``check_type`` via
``compute_check_rating`` and picks the higher-rated one — deterministic, no
dice roll (ADR-0019), never inventing an action outside ``reaction_actions``
(ADR-0032).

This test proves the twin is reachable on the REAL path: a condition-granted
guardian (mirrors ``test_interpose_damage_path.py``'s
``ConditionCapabilityEffect`` setup) drives interpose through
``apply_damage_to_participant`` -> ``_try_interpose`` ->
``dispatch_interpose(select_best_check_rating=True)``, and we capture which
``check_type`` actually reaches ``perform_check``
(``world.mechanics.challenge_resolution.perform_check``).

Tagged @tag("postgres") because apply_condition (capability grant) uses
DISTINCT ON in get_available_actions, which fails on the SQLite fast tier —
same constraint as InterposeReducesAllyDamageTest in
test_interpose_damage_path.py.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, tag

from world.combat.constants import CombatManeuver, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatRoundAction,
)
from world.combat.interpose_content import ensure_interpose_content
from world.scenes.constants import RoundStatus
from world.seeds.combat_checks import seed_combat_check_content
from world.traits.models import PointConversionRange, TraitType
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


@tag("postgres")  # apply_condition (capability grant) uses DISTINCT ON (PG-only)
class InterposeBestOfCheckRealPathTest(TestCase):
    """The Melee-Defense twin is reachable through a condition-granted guardian.

    Builds a guardian granted the ``telekinesis`` interpose capability via a
    condition (the majority real-world path — trait-derived capabilities are
    the minority), stats them for one CheckType or the other, drives the
    interpose dispatch through ``apply_damage_to_participant``, and asserts
    which ``check_type`` actually reached ``perform_check``.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        # ensure_interpose_content() must run AFTER seed_combat_check_content()
        # so its Melee-Defense twin approaches aren't skipped (interpose_content
        # warns + no-ops without a seeded "Melee Defense" CheckType).
        seed_combat_check_content()
        ensure_interpose_content()

        from world.areas.positioning.plummet_content import ensure_catch_content
        from world.traits.factories import CheckSystemSetupFactory
        from world.traits.models import ResultChart

        # ensure_catch_content wires the "wits" CheckTypeTrait onto the shared
        # Reflexes CheckType (the base interpose approaches reuse it).
        ensure_catch_content()

        # Seed the check-resolution pipeline (ResultCharts + outcomes for rank
        # diffs). Without this, _get_difficulty_indicator_for_check finds no
        # chart for either check's roll -> IMPOSSIBLE -> the approach is dropped.
        CheckSystemSetupFactory.create()
        ResultChart.clear_cache()

        # compute_check_rating needs a stat/skill -> points conversion, or every
        # trait value converts to 0 points and the two branches can never diverge.
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.SKILL,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )

    def _run_interpose_and_capture_check_type(
        self,
        *,
        wits: int,
        agility: int,
        melee_combat: int,
    ) -> str:
        """Build one guardian+ally encounter, drive interpose, return the check_type name.

        *wits* feeds the Reflexes CheckType (the base twin); *agility* +
        *melee_combat* feed the Melee Defense CheckType (the #2207 twin).
        """
        from evennia import create_object

        from world.character_sheets.factories import CharacterSheetFactory
        from world.checks.types import CheckResult
        from world.conditions.factories import (
            ConditionCapabilityEffectFactory,
            ConditionTemplateFactory,
        )
        from world.conditions.models import CapabilityType
        from world.conditions.services import apply_condition
        from world.mechanics.models import ChallengeInstance, ChallengeTemplate
        from world.traits.factories import CheckOutcomeFactory
        from world.traits.models import CharacterTraitValue, Trait

        room = create_object("typeclasses.rooms.Room", key="InterposeBestOfRoom", nohome=True)
        encounter = CombatEncounterFactory(
            status=RoundStatus.RESOLVING,
            round_number=1,
            room=room,
        )

        guardian_sheet = CharacterSheetFactory()
        guardian_participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=guardian_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        guardian = guardian_sheet.character
        guardian.db_location = room
        guardian.save(update_fields=["db_location"])

        ally_sheet = CharacterSheetFactory()
        ally_participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        ally = ally_sheet.character
        ally.db_location = room
        ally.save(update_fields=["db_location"])

        # Grant Guardian telekinesis via a condition — the real, majority path
        # (_get_condition_sources sets capability_name="", proving selection
        # can't rely on the dead name-match).
        telekinesis = CapabilityType.objects.get(name="telekinesis")
        grant_template = ConditionTemplateFactory(name=f"TelekineticGuardian-{guardian.id}")
        ConditionCapabilityEffectFactory(condition=grant_template, capability=telekinesis, value=10)
        apply_condition(guardian, grant_template)

        # Stat the guardian per this branch.
        wits_trait = Trait.objects.get(name="wits")
        agility_trait = Trait.objects.get(name="agility")
        melee_trait = Trait.objects.get(name="Melee Combat")
        CharacterTraitValue.objects.create(character=guardian, trait=wits_trait, value=wits)
        CharacterTraitValue.objects.create(character=guardian, trait=agility_trait, value=agility)
        CharacterTraitValue.objects.create(
            character=guardian, trait=melee_trait, value=melee_combat
        )

        ally_vitals = _make_vitals(ally_participant, health=100, max_health=100)
        _make_vitals(guardian_participant)

        CombatRoundAction.objects.create(
            participant=guardian_participant,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target=ally_participant,
            is_ready=True,
        )

        # Pre-bind the Interpose ChallengeInstance to Ally (mirrors
        # _ensure_interpose_challenges).
        template = ChallengeTemplate.objects.get(name="Interpose")
        ChallengeInstance.objects.get_or_create(
            template=template,
            target_object=ally,
            is_active=True,
            defaults={"location": room, "is_revealed": True},
        )

        success = CheckOutcomeFactory(name=f"CleanBlock-{guardian.id}", success_level=2)
        captured_check_types: list[str] = []

        def _fake_perform_check(character, check_type, *args, **kwargs):
            captured_check_types.append(check_type.name)
            return CheckResult(
                check_type=check_type,
                outcome=success,
                chart=None,
                roller_rank=None,
                target_rank=None,
                rank_difference=0,
                trait_points=0,
                aspect_bonus=0,
                total_points=0,
            )

        from world.combat.services import apply_damage_to_participant

        with patch(
            "world.mechanics.challenge_resolution.perform_check",
            side_effect=_fake_perform_check,
        ):
            apply_damage_to_participant(ally_participant, 40)

        ally_vitals.refresh_from_db()
        self.assertEqual(
            len(captured_check_types),
            1,
            "interpose must dispatch through perform_check exactly once",
        )
        return captured_check_types[0]

    def test_best_of_check_picks_higher_rated_reaction_action(self) -> None:
        """Duelist build -> Melee Defense rolls; Reflexes build -> Reflexes rolls."""
        # Duelist-statted guardian: high agility + Melee Combat, low wits.
        duelist_check_type = self._run_interpose_and_capture_check_type(
            wits=1, agility=30, melee_combat=30
        )
        self.assertEqual(
            duelist_check_type,
            "Melee Defense",
            "a duelist-statted guardian must roll the Melee-Defense twin, not Reflexes",
        )

        # Reflexes-statted guardian: high wits, low agility/Melee Combat.
        reflexive_check_type = self._run_interpose_and_capture_check_type(
            wits=30, agility=1, melee_combat=1
        )
        self.assertEqual(
            reflexive_check_type,
            "Reflexes",
            "a reflexes-statted guardian must roll the base Reflexes approach",
        )
