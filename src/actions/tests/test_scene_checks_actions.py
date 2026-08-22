"""Tests for scene check invocation (#3295): self-checks, GM calls, proposals.

Covers the ruling's hard invariant -- every check anyone rolls is an authored
CheckType at a DifficultyChoice band, never a freeform stat/skill/difficulty
invention -- restated as the same style of firewall tests #2118 wrote for the
SENIOR ad-hoc action, plus the new journeys: self-check broadcast, call ->
answer -> broadcast, decline, synthesized-CheckType exclusion, and a SENIOR
regression check through the extracted ``world.checks.catalog_invocation`` core.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from actions.definitions.gm_adjudication import InvokeCatalogCheckAction
from actions.definitions.scene_checks import (
    AnswerCheckCallAction,
    CallForCheckAction,
    DeclineCheckCallAction,
    ProposeCheckAction,
    SceneSelfCheckAction,
)
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.constants import CheckCallTargetStatus
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.checks.models import CheckCall, CheckCallTarget
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.player_submissions.models import CheckProposal
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import DifficultyChoice
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Interaction
from world.traits.constants import TraitType
from world.traits.factories import CheckSystemSetupFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitCategory,
)


def _room(*, db_key: str = "SceneCheckRoom") -> object:
    return ObjectDBFactory(db_key=db_key, db_typeclass_path="typeclasses.rooms.Room")


def _pc_in_room(room: object, *, db_key: str) -> tuple[object, object]:
    """Return (Character, Account) -- a PC with a live roster tenure, in *room*."""
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    return char, tenure.player_data.account


class SceneChecksTestBase(TestCase):
    """Shared fixture: room, active scene, a catalog CheckType, a self-check
    player, a JUNIOR GM, and a couple of targets. Built in ``setUp`` (not
    ``setUpTestData``) -- Character typeclass instances hold an Evennia
    ``DbHolder`` attribute proxy that Django's ``setUpTestData`` cannot deepcopy
    (mirrors ``GMAdjudicationActionsTestBase``).
    """

    def setUp(self) -> None:
        Trait.flush_instance_cache()
        CharacterTraitValue.flush_instance_cache()
        ResultChart.clear_cache()

        CheckSystemSetupFactory.create()
        PointConversionRange.objects.get_or_create(
            trait_type=TraitType.STAT,
            min_value=1,
            defaults={"max_value": 100, "points_per_level": 1},
        )
        for rank_val, min_pts, name in [
            (0, 0, "SceneCheckNone"),
            (1, 10, "SceneCheckNovice"),
            (2, 25, "SceneCheckCompetent"),
            (3, 50, "SceneCheckExpert"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val, defaults={"min_points": min_pts, "name": name}
            )

        self.room = _room()
        self.scene = SceneFactory(location=self.room)

        self.player_actor, self.player_account = _pc_in_room(self.room, db_key="SelfChecker")
        SceneParticipationFactory(scene=self.scene, account=self.player_account, is_gm=False)

        self.gm_actor, self.gm_account = _pc_in_room(self.room, db_key="CallingGM")
        GMProfileFactory(account=self.gm_account, level=GMLevel.JUNIOR)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)

        self.target_actor, self.target_account = _pc_in_room(self.room, db_key="CalledTarget")
        SceneParticipationFactory(scene=self.scene, account=self.target_account, is_gm=False)

        self.check_trait, _ = Trait.objects.get_or_create(
            name="scene_check_strength",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL},
        )
        self.check_category = CheckCategoryFactory(name="scene_check_combat")
        self.check_type = CheckTypeFactory(name="Riverside Tracking", category=self.check_category)
        CheckTypeTraitFactory(
            check_type=self.check_type, trait=self.check_trait, weight=Decimal("1.0")
        )

        for actor in (self.player_actor, self.target_actor):
            CharacterTraitValue.objects.get_or_create(
                character=actor.sheet_data, trait=self.check_trait, defaults={"value": 30}
            )

    def _promote_gm_to_senior(self) -> None:
        """Raise the fixture GM's existing profile to SENIOR (never a second row --
        GMProfile.account is OneToOne)."""
        profile = self.gm_account.gm_profile
        profile.level = GMLevel.SENIOR
        profile.save(update_fields=["level"])


class SceneSelfCheckActionTests(SceneChecksTestBase):
    def test_any_player_can_self_check(self) -> None:
        result = SceneSelfCheckAction().run(
            actor=self.player_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.NORMAL,
        )
        self.assertTrue(result.success, result.message)
        self.assertIn(self.check_type.name, result.message)

    def test_self_check_broadcasts_to_the_room_as_the_presenting_persona(self) -> None:
        from world.scenes.services import active_persona_for_sheet

        persona = active_persona_for_sheet(self.player_actor.sheet_data)
        SceneSelfCheckAction().run(
            actor=self.player_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.NORMAL,
        )
        interaction = Interaction.objects.filter(mode=InteractionMode.OUTCOME).latest("timestamp")
        self.assertIn(persona.name, interaction.content)
        self.assertIn(self.check_type.name, interaction.content)
        self.assertEqual(interaction.scene_id, self.scene.pk)

    def test_unresolvable_check_ref_refuses_with_discovery_hint(self) -> None:
        result = SceneSelfCheckAction().run(
            actor=self.player_actor,
            check_type_ref="Nonexistent Check",
            difficulty=DifficultyChoice.NORMAL,
        )
        self.assertFalse(result.success)
        self.assertIn("check find", result.message)

    def test_integer_difficulty_is_rejected(self) -> None:
        result = SceneSelfCheckAction().run(
            actor=self.player_actor,
            check_type_ref=self.check_type.name,
            difficulty=60,
        )
        self.assertFalse(result.success)
        self.assertIn("difficulty band", result.message)

    def test_actor_without_sheet_is_refused(self) -> None:
        bare = ObjectDBFactory(
            db_key="NoSheetActor", db_typeclass_path="typeclasses.characters.Character"
        )
        result = SceneSelfCheckAction().run(
            actor=bare,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.NORMAL,
        )
        self.assertFalse(result.success)

    def test_stat_skill_and_consequence_pool_kwargs_are_never_consumed(self) -> None:
        """Firewall (mirrors #2118): invention-shaped kwargs are inert."""
        baseline = SceneSelfCheckAction().run(
            actor=self.player_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.TRIVIAL,
        )
        with_extras = SceneSelfCheckAction().run(
            actor=self.player_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.TRIVIAL,
            stat="strength",
            skill="athletics",
            consequence_pool_id=999,
            consequence_pool="whatever",
        )
        self.assertTrue(baseline.success)
        self.assertTrue(with_extras.success)


class SynthesizedCheckTypeExclusionTests(SceneChecksTestBase):
    """The picker/resolution queryset excludes another character's owner_sheet
    row -- only the invoking character's own synthesized check is visible."""

    def setUp(self) -> None:
        super().setUp()
        self.own_synth = CheckTypeFactory(
            name="Player's Own Signature Working",
            category=self.check_category,
            owner_sheet=self.player_actor.sheet_data,
        )
        CheckTypeTraitFactory(
            check_type=self.own_synth, trait=self.check_trait, weight=Decimal("1.0")
        )
        self.other_synth = CheckTypeFactory(
            name="Someone Else's Signature Working",
            category=self.check_category,
            owner_sheet=self.target_actor.sheet_data,
        )
        CheckTypeTraitFactory(
            check_type=self.other_synth, trait=self.check_trait, weight=Decimal("1.0")
        )

    def test_own_synthesized_check_type_resolves(self) -> None:
        result = SceneSelfCheckAction().run(
            actor=self.player_actor,
            check_type_ref=self.own_synth.name,
            difficulty=DifficultyChoice.NORMAL,
        )
        self.assertTrue(result.success, result.message)

    def test_other_characters_synthesized_check_type_does_not_resolve(self) -> None:
        result = SceneSelfCheckAction().run(
            actor=self.player_actor,
            check_type_ref=self.other_synth.name,
            difficulty=DifficultyChoice.NORMAL,
        )
        self.assertFalse(result.success)

    def test_other_characters_synthesized_check_type_excluded_from_call(self) -> None:
        """A GM's call-for-check catalog resolution never sees ANY owner_sheet row."""
        result = CallForCheckAction().run(
            actor=self.gm_actor,
            check_type_ref=self.own_synth.name,
            difficulty=DifficultyChoice.NORMAL,
            targets=[self.target_actor],
        )
        self.assertFalse(result.success)


class CallForCheckActionTests(SceneChecksTestBase):
    def test_non_gm_is_refused(self) -> None:
        result = CallForCheckAction().run(
            actor=self.player_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.NORMAL,
            targets=[self.target_actor],
        )
        self.assertFalse(result.success)

    def test_junior_gm_can_call_and_creates_call_and_target_rows(self) -> None:
        result = CallForCheckAction().run(
            actor=self.gm_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
            targets=[self.target_actor],
        )
        self.assertTrue(result.success, result.message)
        call = CheckCall.objects.get()
        self.assertEqual(call.check_type_id, self.check_type.pk)
        self.assertEqual(call.band, DifficultyChoice.HARD)
        self.assertEqual(call.scene_id, self.scene.pk)
        target_row = CheckCallTarget.objects.get(call=call)
        self.assertEqual(target_row.target_sheet_id, self.target_actor.sheet_data.pk)
        self.assertEqual(target_row.status, CheckCallTargetStatus.PENDING)

    def test_call_with_int_targets_resolves_rest_shape(self) -> None:
        """REST dispatch sends plain int pks, not resolved ObjectDBs (#2163/#3070)."""
        result = CallForCheckAction().run(
            actor=self.gm_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.NORMAL,
            targets=[self.target_actor.pk],
        )
        self.assertTrue(result.success, result.message)
        self.assertEqual(CheckCallTarget.objects.count(), 1)

    def test_call_without_targets_refuses(self) -> None:
        result = CallForCheckAction().run(
            actor=self.gm_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.NORMAL,
            targets=[],
        )
        self.assertFalse(result.success)

    def test_call_without_active_scene_refuses(self) -> None:
        lone_room = _room(db_key="NoSceneRoom")
        lone_gm, lone_gm_account = _pc_in_room(lone_room, db_key="LoneGM")
        GMProfileFactory(account=lone_gm_account, level=GMLevel.JUNIOR)
        lone_target, _ = _pc_in_room(lone_room, db_key="LoneTarget")

        result = CallForCheckAction().run(
            actor=lone_gm,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.NORMAL,
            targets=[lone_target],
        )
        self.assertFalse(result.success)
        self.assertEqual(CheckCall.objects.count(), 0)

    def test_call_broadcasts_room_visible_prompt(self) -> None:
        CallForCheckAction().run(
            actor=self.gm_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.NORMAL,
            targets=[self.target_actor],
        )
        interaction = Interaction.objects.filter(mode=InteractionMode.OUTCOME).latest("timestamp")
        self.assertIn(self.check_type.name, interaction.content)
        self.assertIn("calls for a check", interaction.content)

    def test_stat_skill_and_consequence_pool_kwargs_are_never_consumed(self) -> None:
        """Firewall (mirrors #2118): invention-shaped kwargs are inert."""
        baseline = CallForCheckAction().run(
            actor=self.gm_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.TRIVIAL,
            targets=[self.target_actor],
        )
        self.assertTrue(baseline.success)
        CheckCallTarget.objects.all().delete()
        CheckCall.objects.all().delete()
        with_extras = CallForCheckAction().run(
            actor=self.gm_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.TRIVIAL,
            targets=[self.target_actor],
            stat="strength",
            skill="athletics",
            consequence_pool_id=999,
            consequence_pool="whatever",
        )
        self.assertTrue(with_extras.success)


class AnswerAndDeclineCheckCallActionTests(SceneChecksTestBase):
    def setUp(self) -> None:
        super().setUp()
        call_result = CallForCheckAction().run(
            actor=self.gm_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
            targets=[self.target_actor],
        )
        self.call_id = call_result.data["call_id"]

    def test_target_answers_call_marks_answered_and_broadcasts(self) -> None:
        result = AnswerCheckCallAction().run(actor=self.target_actor, call_id=self.call_id)
        self.assertTrue(result.success, result.message)
        self.assertIn(self.check_type.name, result.message)

        target_row = CheckCallTarget.objects.get(call_id=self.call_id)
        self.assertEqual(target_row.status, CheckCallTargetStatus.ANSWERED)
        self.assertIsNotNone(target_row.resolved_at)

    def test_answer_is_bound_to_the_calls_own_check_and_band_not_a_free_pick(self) -> None:
        result = AnswerCheckCallAction().run(actor=self.target_actor, call_id=self.call_id)
        band_label = DifficultyChoice(DifficultyChoice.HARD).label
        self.assertIn(band_label, result.message)

    def test_answering_twice_refuses_the_second_time(self) -> None:
        AnswerCheckCallAction().run(actor=self.target_actor, call_id=self.call_id)
        second = AnswerCheckCallAction().run(actor=self.target_actor, call_id=self.call_id)
        self.assertFalse(second.success)

    def test_non_target_cannot_answer(self) -> None:
        result = AnswerCheckCallAction().run(actor=self.player_actor, call_id=self.call_id)
        self.assertFalse(result.success)

    def test_target_declines_marks_declined_with_no_broadcast(self) -> None:
        before = Interaction.objects.filter(mode=InteractionMode.OUTCOME).count()
        result = DeclineCheckCallAction().run(actor=self.target_actor, call_id=self.call_id)
        self.assertTrue(result.success, result.message)
        target_row = CheckCallTarget.objects.get(call_id=self.call_id)
        self.assertEqual(target_row.status, CheckCallTargetStatus.DECLINED)
        after = Interaction.objects.filter(mode=InteractionMode.OUTCOME).count()
        self.assertEqual(before, after)

    def test_declining_twice_refuses_the_second_time(self) -> None:
        DeclineCheckCallAction().run(actor=self.target_actor, call_id=self.call_id)
        second = DeclineCheckCallAction().run(actor=self.target_actor, call_id=self.call_id)
        self.assertFalse(second.success)

    def test_declining_then_answering_refuses(self) -> None:
        DeclineCheckCallAction().run(actor=self.target_actor, call_id=self.call_id)
        answer = AnswerCheckCallAction().run(actor=self.target_actor, call_id=self.call_id)
        self.assertFalse(answer.success)

    def test_stat_skill_and_consequence_pool_kwargs_never_consumed_on_answer(self) -> None:
        """Firewall (mirrors #2118): invention-shaped kwargs are inert on answer too."""
        result = AnswerCheckCallAction().run(
            actor=self.target_actor,
            call_id=self.call_id,
            stat="strength",
            skill="athletics",
            consequence_pool_id=999,
        )
        self.assertTrue(result.success, result.message)


class ProposeCheckActionTests(SceneChecksTestBase):
    def test_propose_creates_a_check_proposal_row(self) -> None:
        result = ProposeCheckAction().run(
            actor=self.player_actor,
            proposed_name="Riverside Tracking II",
            intent="Following a cold trail through mud.",
            situation_text="Chasing a fleeing suspect through wetlands.",
            suggested_traits_text="Perception + Survival",
        )
        self.assertTrue(result.success, result.message)
        proposal = CheckProposal.objects.get()
        self.assertEqual(proposal.proposed_name, "Riverside Tracking II")
        self.assertEqual(proposal.submitted_by_account, self.player_account)

    def test_propose_never_creates_a_live_check_type(self) -> None:
        from world.checks.models import CheckType

        ProposeCheckAction().run(
            actor=self.player_actor,
            proposed_name="Riverside Tracking II",
            intent="Following a cold trail.",
            situation_text="Chasing a suspect.",
        )
        self.assertEqual(CheckType.objects.filter(name="Riverside Tracking II").count(), 0)

    def test_propose_requires_name_intent_and_situation(self) -> None:
        result = ProposeCheckAction().run(
            actor=self.player_actor,
            proposed_name="",
            intent="",
            situation_text="",
        )
        self.assertFalse(result.success)


class SeniorAdHocRegressionThroughExtractedCoreTests(SceneChecksTestBase):
    """#2118's SENIOR ad-hoc action must behave identically after its catalog
    resolve/find/band-validation core moved to ``world.checks.catalog_invocation``."""

    def test_senior_gm_can_still_invoke_via_the_extracted_core(self) -> None:
        self._promote_gm_to_senior()
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target_actor,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
        )
        self.assertTrue(result.success, result.message)

    def test_senior_find_mode_still_lists_the_catalog(self) -> None:
        self._promote_gm_to_senior()
        result = InvokeCatalogCheckAction().run(actor=self.gm_actor, query="Riverside")
        self.assertTrue(result.success)
        self.assertIn(self.check_type.name, result.message)

    def test_senior_unresolvable_ref_still_hints_gm_find(self) -> None:
        self._promote_gm_to_senior()
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target_actor,
            check_type_ref="Nonexistent Check",
            difficulty=DifficultyChoice.HARD,
        )
        self.assertFalse(result.success)
        self.assertIn("gm check find", result.message)
