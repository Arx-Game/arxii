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


class TechniqueGuardianBarrierResolutionTest(TestCase):
    """Journey test: a technique guardian's BARRIER resolution (#2207 Task 3).

    A guardian who knows Aegis Field (the seeded barrier-flavor protective
    technique, `world.magic.effect_palette_content.ensure_force_field_content`)
    declares Interpose "with" it on a named ally. Damage lands on the ally and
    drives the REAL dispatch path: `apply_damage_to_participant` ->
    `_try_interpose` -> (`action.focused_action_id` is set) ->
    `_try_technique_interpose`, which rolls the guardian's own cast check
    (`resolve_cast_check_type`) instead of a capability-reaction challenge and
    pays anima instead of fatigue.

    `perform_check` is mocked at the seam `_try_technique_interpose` actually
    calls (`world.combat.services.perform_check`, imported at module scope from
    `world.checks.services` — the same name `dispatch_interpose`'s sibling
    call at services.py:745 resolves through) to force a clean success and
    capture the `check_type` argument.

    Untagged (SQLite fast tier): unlike `InterposeBestOfCheckRealPathTest`
    above, this path never calls `apply_condition`/`get_available_actions`
    (no DISTINCT ON dependency) — the technique branch classifies the
    guardian's already-known technique via authored `condition_applications`
    data and rolls a plain cast check, not a capability-reaction challenge.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        from world.magic.effect_palette_content import ensure_force_field_content

        # Seeds the "Interpose" ChallengeTemplate (severity=3, the shared
        # target_difficulty both mundane and technique interpose roll against).
        ensure_interpose_content()
        # Seeds the "Aegis Field" barrier-flavor Technique + its ConditionTemplate
        # (reactive_anima_cost) the technique branch reads.
        ensure_force_field_content()

    def test_technique_guardian_barrier_debits_anima_and_zeroes_damage(self) -> None:
        """Clean success: guardian's cast check rolled, anima debited, ally damage zeroed."""
        from types import SimpleNamespace

        from evennia import create_object

        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.services import apply_damage_to_participant
        from world.magic.effect_palette_content import FORCE_FIELD_TECHNIQUE_NAME
        from world.magic.factories import CharacterAnimaFactory
        from world.magic.models import CharacterTechnique, Technique
        from world.magic.services.anima import resolve_cast_check_type

        room = create_object("typeclasses.rooms.Room", key="TechGuardianBarrierRoom", nohome=True)
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

        # The guardian knows Aegis Field (real seeded content, not a test double).
        aegis_field = Technique.objects.get(name=FORCE_FIELD_TECHNIQUE_NAME)
        CharacterTechnique.objects.create(character=guardian_sheet, technique=aegis_field)

        starting_anima = 10
        anima = CharacterAnimaFactory(character=guardian, current=starting_anima, maximum=10)
        expected_cost = aegis_field.condition_applications.get().condition.reactive_anima_cost
        self.assertGreater(
            expected_cost,
            0,
            "Aegis Field's reactive_anima_cost must be positive to prove the debit",
        )

        ally_vitals = _make_vitals(ally_participant, health=100, max_health=100)
        _make_vitals(guardian_participant)

        # Build the CombatRoundAction row directly (encounter is already
        # RESOLVING here, so declare_interpose's DECLARING-status gate would
        # reject it) — same row shape declare_interpose(technique=...) (Task 2)
        # produces once validated: focused_action set, maneuver=INTERPOSE,
        # focused_ally_target=ally.
        CombatRoundAction.objects.create(
            participant=guardian_participant,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            focused_ally_target=ally_participant,
            focused_action=aegis_field,
            is_ready=True,
        )

        expected_check_type = resolve_cast_check_type(guardian, aegis_field.action_template)
        captured_check_types: list = []

        def _fake_perform_check(character, check_type, *args, **kwargs):
            captured_check_types.append(check_type)
            return SimpleNamespace(success_level=2)

        with patch(
            "world.combat.services.perform_check",
            side_effect=_fake_perform_check,
        ):
            apply_damage_to_participant(ally_participant, 40)

        ally_vitals.refresh_from_db()
        anima.refresh_from_db()

        self.assertEqual(
            len(captured_check_types),
            1,
            "technique interpose must roll perform_check exactly once",
        )
        self.assertEqual(
            captured_check_types[0],
            expected_check_type,
            "the technique branch must roll the guardian's own cast check, "
            "not a capability-reaction challenge",
        )
        self.assertEqual(
            anima.current,
            starting_anima - expected_cost,
            "the guardian's anima must be debited by the technique's reactive_anima_cost",
        )
        self.assertEqual(
            ally_vitals.health,
            100,
            "a forced clean success must zero the damage reaching the ally",
        )

    def test_situation_ctx_threaded_with_live_round_context(self) -> None:
        """#2536 Task 5 review fix: `_try_technique_interpose` must thread a
        SituationContext into the guardian's own cast check —
        ``action.participant`` is already dereferenced elsewhere in the
        function (``current_position``), so this plumbing must not be
        skipped, or a future CHECK_BONUS perk scoped to the guardian's
        protective-technique CheckType would silently never fire.

        Calls ``_try_technique_interpose`` directly (rather than the full
        ``apply_damage_to_participant`` dispatch chain the sibling test
        above exercises) to keep this a focused unit test of the threading.
        """
        from types import SimpleNamespace

        from evennia import create_object

        from flows.events.payloads import DamagePreApplyPayload, DamageSource
        from world.character_sheets.factories import CharacterSheetFactory
        from world.combat.round_context import CombatRoundContext
        from world.combat.services import _try_technique_interpose
        from world.covenants.perks.context import SituationContext
        from world.magic.effect_palette_content import FORCE_FIELD_TECHNIQUE_NAME
        from world.magic.factories import CharacterAnimaFactory
        from world.magic.models import CharacterTechnique, Technique

        room = create_object("typeclasses.rooms.Room", key="TechGuardianSituationRoom", nohome=True)
        encounter = CombatEncounterFactory(status=RoundStatus.RESOLVING, round_number=1, room=room)

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
        ally = ally_sheet.character

        aegis_field = Technique.objects.get(name=FORCE_FIELD_TECHNIQUE_NAME)
        CharacterTechnique.objects.create(character=guardian_sheet, technique=aegis_field)
        CharacterAnimaFactory(character=guardian, current=10, maximum=10)

        action = CombatRoundAction.objects.create(
            participant=guardian_participant,
            round_number=1,
            maneuver=CombatManeuver.INTERPOSE,
            focused_action=aegis_field,
            is_ready=True,
        )
        pre_payload = DamagePreApplyPayload(
            target=ally,
            amount=40,
            damage_type=None,
            source=DamageSource(type="character", ref=ally),
        )

        with patch(
            "world.combat.services.perform_check",
            return_value=SimpleNamespace(success_level=2),
        ) as mock_perform:
            _try_technique_interpose(action, guardian, ally, pre_payload)

        situation_ctx = mock_perform.call_args.kwargs["situation_ctx"]
        self.assertIsInstance(situation_ctx, SituationContext)
        self.assertEqual(situation_ctx.holder, guardian_participant.character_sheet)
        self.assertEqual(situation_ctx.subject, guardian_participant.character_sheet)
        self.assertIsNone(situation_ctx.target)
        self.assertIsInstance(situation_ctx.resolution, CombatRoundContext)
        self.assertEqual(situation_ctx.resolution.participant, guardian_participant)
