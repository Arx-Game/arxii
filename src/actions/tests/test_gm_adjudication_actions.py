"""Tests for the GM adjudication toolkit Actions (#2118).

Covers ``InvokeCatalogCheckAction``, ``GMAwardAction``, ``GMApplyConditionAction`` --
permission journeys (scene-GM pass, non-GM refusal, staff bypass, JUNIOR floor on
award/condition) and the RATIFIED no-invention invariant: no code path accepts a
stat/skill pair, an integer difficulty, or any consequence-pool reference from a GM.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.test import TestCase

from actions.definitions.gm_adjudication import (
    GMApplyConditionAction,
    GMAwardAction,
    GMListConditionsAction,
    GMRemoveConditionAction,
    InvokeCatalogCheckAction,
)
from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.achievements.constants import AccessChangeSource
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.classes.models import PathStage
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.currency.models import FavorTokenDetails
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.magic.constants import AcquisitionOrigin, GiftKind, TargetKind
from world.magic.factories import GiftFactory, ResonanceFactory, TechniqueFactory
from world.magic.models import CharacterGift, CharacterTechnique, Thread
from world.narrative.models import NarrativeMessage
from world.progression.models import DevelopmentPoints, ExperiencePointsData, MaturationStatCap
from world.progression.types import ProgressionReason
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.action_constants import DifficultyChoice
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Interaction
from world.scenes.narrator import NARRATOR_PERSONA_NAME
from world.scenes.services import active_persona_for_sheet
from world.societies.factories import OrganizationFactory
from world.traits.constants import STAT_DISPLAY_DIVISOR
from world.traits.factories import CheckSystemSetupFactory, TraitFactory
from world.traits.models import (
    CharacterTraitChange,
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitCategory,
    TraitChangeSource,
    TraitType,
)


def _room(*, db_key: str = "AdjudicationRoom") -> object:
    return ObjectDBFactory(db_key=db_key, db_typeclass_path="typeclasses.rooms.Room")


def _pc_in_room(room: object, *, db_key: str) -> tuple[object, object]:
    """Return (Character, Account) -- a PC with a live roster tenure, located in *room*."""
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    return char, tenure.player_data.account


class GMAdjudicationActionsTestBase(TestCase):
    """Shared fixture: room, scene, GM/non-GM/staff actors, a check catalog + target.

    Built in ``setUp`` (per test), not ``setUpTestData`` -- Character typeclass
    instances hold an Evennia ``DbHolder`` attribute proxy that Django's
    ``setUpTestData`` cannot deepcopy for per-test isolation (mirrors
    ``GMCombatActionTestBase`` in ``test_gm_combat_actions.py``).
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
            (0, 0, "AdjNone"),
            (1, 10, "AdjNovice"),
            (2, 25, "AdjCompetent"),
            (3, 50, "AdjExpert"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val, defaults={"min_points": min_pts, "name": name}
            )

        self.room = _room()
        self.scene = SceneFactory(location=self.room)

        self.gm_actor, self.gm_account = _pc_in_room(self.room, db_key="GMActor")
        GMProfileFactory(account=self.gm_account, level=GMLevel.SENIOR)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)

        self.starting_gm_actor, self.starting_gm_account = _pc_in_room(
            self.room, db_key="StartingGMActor"
        )
        GMProfileFactory(account=self.starting_gm_account, level=GMLevel.STARTING)
        SceneParticipationFactory(scene=self.scene, account=self.starting_gm_account, is_gm=True)

        self.junior_gm_actor, self.junior_gm_account = _pc_in_room(
            self.room, db_key="JuniorGMActor"
        )
        GMProfileFactory(account=self.junior_gm_account, level=GMLevel.JUNIOR)
        SceneParticipationFactory(scene=self.scene, account=self.junior_gm_account, is_gm=True)

        self.player_actor, self.player_account = _pc_in_room(self.room, db_key="PlayerActor")
        SceneParticipationFactory(scene=self.scene, account=self.player_account, is_gm=False)

        self.staff_account = AccountFactory(username="staff_adjudication", is_staff=True)
        self.staff_actor = CharacterFactory(db_key="StaffActor", location=self.room)
        self.staff_actor.db_account = self.staff_account
        self.staff_actor.save()

        self.target, self.target_account = _pc_in_room(self.room, db_key="TargetActor")

        self.check_trait, _ = Trait.objects.get_or_create(
            name="adj_check_strength",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL},
        )
        self.check_category = CheckCategoryFactory(name="adj_check_combat")
        self.check_type = CheckTypeFactory(name="Power Strike", category=self.check_category)
        CheckTypeTraitFactory(
            check_type=self.check_type, trait=self.check_trait, weight=Decimal("1.0")
        )

        self.dev_trait = TraitFactory(name="adj_dev_skill", trait_type=TraitType.SKILL)

        self.condition_template = ConditionTemplateFactory(name="Adjudication Winded")

        CharacterTraitValue.objects.get_or_create(
            character=self.target.sheet_data, trait=self.check_trait, defaults={"value": 30}
        )


class InvokeCatalogCheckActionPermissionTests(GMAdjudicationActionsTestBase):
    def test_non_gm_is_refused(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.player_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
        )
        self.assertFalse(result.success)
        self.assertIn("GM trust required", result.message)

    def test_senior_gm_can_invoke(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
        )
        self.assertTrue(result.success)

    def test_staff_bypasses_gm_level_gate(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.staff_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
        )
        self.assertTrue(result.success)

    def test_starting_gm_is_blocked_from_check_invocation(self) -> None:
        """A STARTING-tier GM may not invoke ad-hoc checks (#2857)."""
        result = InvokeCatalogCheckAction().run(
            actor=self.starting_gm_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
        )
        self.assertFalse(result.success)
        self.assertIn("Senior GM or higher", result.message)

    def test_junior_gm_is_blocked_from_check_invocation(self) -> None:
        """A JUNIOR-tier GM may not invoke ad-hoc checks (#2857)."""
        result = InvokeCatalogCheckAction().run(
            actor=self.junior_gm_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
        )
        self.assertFalse(result.success)
        self.assertIn("Senior GM or higher", result.message)

    def test_junior_gm_blocked_from_find_mode(self) -> None:
        """Find/catalog-browse mode shares the SENIOR gate (#2857)."""
        result = InvokeCatalogCheckAction().run(
            actor=self.junior_gm_actor,
            query="Strike",
        )
        self.assertFalse(result.success)
        self.assertIn("Senior GM or higher", result.message)

    def test_senior_gm_can_use_find_mode(self) -> None:
        """Find/catalog-browse mode is available to SENIOR GMs (#2857)."""
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            query="Strike",
        )
        self.assertTrue(result.success)


class InvokeCatalogCheckActionInvocationTests(GMAdjudicationActionsTestBase):
    def test_unresolvable_check_ref_refuses_with_discovery_hint(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target,
            check_type_ref="Nonexistent Check",
            difficulty=DifficultyChoice.HARD,
        )
        self.assertFalse(result.success)
        self.assertIn("gm check find", result.message)

    def test_check_resolves_by_pk(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target,
            check_type_ref=str(self.check_type.pk),
            difficulty=DifficultyChoice.NORMAL,
        )
        self.assertTrue(result.success)
        self.assertIn(self.check_type.name, result.message)

    def test_integer_difficulty_is_rejected(self) -> None:
        """No code path accepts an integer difficulty -- only DifficultyChoice bands."""
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=60,
        )
        self.assertFalse(result.success)
        self.assertIn("difficulty band", result.message)

    def test_all_difficulty_bands_resolve_and_are_number_free(self) -> None:
        for band in DifficultyChoice.values:
            result = InvokeCatalogCheckAction().run(
                actor=self.gm_actor,
                target=self.target,
                check_type_ref=self.check_type.name,
                difficulty=band,
            )
            self.assertTrue(result.success, band)
            self.assertFalse(
                any(ch.isdigit() for ch in result.message),
                f"band {band} leaked a number: {result.message!r}",
            )

    def test_stat_skill_and_consequence_pool_kwargs_are_never_consumed(self) -> None:
        """Extra invention-shaped kwargs (stat/skill/consequence pool refs) are inert.

        No parameter on this Action's code path reads them -- passing them changes
        nothing about the outcome, proving there is no hidden invention surface.
        """
        baseline = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.TRIVIAL,
        )
        with_extras = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.TRIVIAL,
            stat="strength",
            skill="athletics",
            consequence_pool_id=999,
            consequence_pool="whatever",
        )
        self.assertTrue(baseline.success)
        self.assertTrue(with_extras.success)


class InvokeCatalogCheckActionShiftTests(GMAdjudicationActionsTestBase):
    def test_edge_shifts_exactly_one_band_easier_and_echoes_reason(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
            edge_reason="an ally braces the ladder",
        )
        self.assertTrue(result.success)
        self.assertIn("edge", result.message)
        self.assertIn("Normal", result.message)
        self.assertIn("an ally braces the ladder", result.message)

    def test_setback_shifts_exactly_one_band_harder_and_echoes_reason(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
            setback_reason="the footing is treacherous",
        )
        self.assertTrue(result.success)
        self.assertIn("setback", result.message)
        self.assertIn("Daunting", result.message)
        self.assertIn("the footing is treacherous", result.message)

    def test_edge_and_setback_together_is_rejected(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
            edge_reason="help",
            setback_reason="hindrance",
        )
        self.assertFalse(result.success)

    def test_edge_beyond_trivial_is_refused_not_clamped(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.TRIVIAL,
            edge_reason="help",
        )
        self.assertFalse(result.success)
        self.assertIn("easiest", result.message)

    def test_setback_beyond_harrowing_is_refused_not_clamped(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARROWING,
            setback_reason="hindrance",
        )
        self.assertFalse(result.success)
        self.assertIn("hardest", result.message)

    def test_shift_without_reason_is_a_noop_band(self) -> None:
        """An empty edge/setback reason is treated as not shifting at all."""
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.HARD,
            edge_reason="",
        )
        self.assertTrue(result.success)
        self.assertNotIn("edge", result.message)


class InvokeCatalogCheckActionFindTests(GMAdjudicationActionsTestBase):
    def test_find_with_no_target_lists_catalog(self) -> None:
        result = InvokeCatalogCheckAction().run(actor=self.gm_actor)
        self.assertTrue(result.success)
        self.assertIn(self.check_type.name, result.message)

    def test_find_by_name_matches(self) -> None:
        result = InvokeCatalogCheckAction().run(actor=self.gm_actor, query="Power")
        self.assertTrue(result.success)
        self.assertIn(self.check_type.name, result.message)

    def test_find_by_trait_matches(self) -> None:
        result = InvokeCatalogCheckAction().run(actor=self.gm_actor, query="adj_check_strength")
        self.assertTrue(result.success)
        self.assertIn(self.check_type.name, result.message)

    def test_find_with_no_matches(self) -> None:
        result = InvokeCatalogCheckAction().run(actor=self.gm_actor, query="zzz_no_such_check")
        self.assertTrue(result.success)
        self.assertNotIn(self.check_type.name, result.message)

    def test_find_requires_no_gm_level_floor_but_still_needs_scene_gm(self) -> None:
        result = InvokeCatalogCheckAction().run(actor=self.player_actor, query="Power")
        self.assertFalse(result.success)


class RESTTargetResolutionTests(GMAdjudicationActionsTestBase):
    """The REST dispatch path (``dispatch_player_action`` -> ``_dispatch_registry``)
    sends a plain int ``target`` -- no ObjectDB resolution happens before
    ``execute()`` (#3070; see ``actions/CLAUDE.md``'s ``objectdb_target_kwargs``
    note). Each action must resolve that int itself. A ``CharacterSheet``'s pk
    equals its owning ``ObjectDB``'s pk, so the frontend sends the target
    character's plain pk directly -- exactly what these tests pass.
    """

    def test_invoke_check_resolves_int_target(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=self.target.pk,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.NORMAL,
        )
        self.assertTrue(result.success, result.message)
        self.assertIn(self.target.key, result.message)

    def test_invoke_check_int_target_that_does_not_resolve_fails_loud(self) -> None:
        result = InvokeCatalogCheckAction().run(
            actor=self.gm_actor,
            target=999999999,
            check_type_ref=self.check_type.name,
            difficulty=DifficultyChoice.NORMAL,
        )
        self.assertFalse(result.success)

    def test_award_xp_resolves_int_target(self) -> None:
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target.pk,
            award_type="xp",
            amount=10,
        )
        self.assertTrue(result.success, result.message)
        xp_data = ExperiencePointsData.objects.get(account=self.target_account)
        self.assertEqual(xp_data.total_earned, 10)

    def test_apply_condition_resolves_int_target(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target.pk,
            condition_ref=self.condition_template.name,
        )
        self.assertTrue(result.success, result.message)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.target, condition=self.condition_template
            ).exists()
        )


class GMAwardActionTests(GMAdjudicationActionsTestBase):
    def test_non_gm_is_refused(self) -> None:
        result = GMAwardAction().run(
            actor=self.player_actor, target=self.target, award_type="xp", amount=10
        )
        self.assertFalse(result.success)

    def test_junior_floor_enforced(self) -> None:
        result = GMAwardAction().run(
            actor=self.starting_gm_actor, target=self.target, award_type="xp", amount=10
        )
        self.assertFalse(result.success)
        self.assertIn("Junior GM", result.message)

    def test_staff_bypasses_junior_floor(self) -> None:
        result = GMAwardAction().run(
            actor=self.staff_actor, target=self.target, award_type="xp", amount=10
        )
        self.assertTrue(result.success)

    def test_award_xp_creates_transaction_with_gm_reason(self) -> None:
        from world.progression.models import XPTransaction

        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="xp",
            amount=15,
            description="heroic rescue",
        )
        self.assertTrue(result.success)
        xp_data = ExperiencePointsData.objects.get(account=self.target_account)
        self.assertEqual(xp_data.total_earned, 15)
        txn = XPTransaction.objects.get(account=self.target_account)
        self.assertEqual(txn.reason, ProgressionReason.GM_AWARD)
        self.assertEqual(txn.gm, self.gm_account)
        self.assertEqual(txn.description, "heroic rescue")

    def test_award_xp_rejects_non_positive_amount(self) -> None:
        result = GMAwardAction().run(
            actor=self.gm_actor, target=self.target, award_type="xp", amount=0
        )
        self.assertFalse(result.success)
        self.assertFalse(ExperiencePointsData.objects.filter(account=self.target_account).exists())

    def test_award_development_creates_transaction(self) -> None:
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="development",
            trait_ref=self.dev_trait.name,
            amount=5,
            description="training montage",
        )
        self.assertTrue(result.success, result.message)
        dp = DevelopmentPoints.objects.get(
            character_sheet=self.target.sheet_data, trait=self.dev_trait
        )
        self.assertEqual(dp.total_earned, 5)

    def test_award_development_requires_trait_ref(self) -> None:
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="development",
            amount=5,
        )
        self.assertFalse(result.success)

    def test_invalid_award_type_is_rejected(self) -> None:
        result = GMAwardAction().run(
            actor=self.gm_actor, target=self.target, award_type="legend", amount=5
        )
        self.assertFalse(result.success)

    def test_award_favor_token_mints_with_provenance(self) -> None:
        org = OrganizationFactory()
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="favor_token",
            org_ref=str(org.pk),
            description="Cleared the Thornwood ambush",
        )
        self.assertTrue(result.success)
        token = FavorTokenDetails.objects.get(issuing_organization=org)
        self.assertEqual(token.provenance_note, "Cleared the Thornwood ambush")
        target_sheet_pk = self.target.character_sheet.pk
        self.assertEqual(token.item_instance.holder_character_sheet_id, target_sheet_pk)

    def test_award_favor_token_resolves_org_by_name(self) -> None:
        org = OrganizationFactory(name="The Golden Hare Academy")
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="favor_token",
            org_ref="The Golden Hare Academy",
            description="Sponsored the prospect's trial",
        )
        self.assertTrue(result.success)
        self.assertTrue(FavorTokenDetails.objects.filter(issuing_organization=org).exists())

    def test_award_favor_token_requires_org_ref(self) -> None:
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="favor_token",
            description="Cleared the Thornwood ambush",
        )
        self.assertFalse(result.success)
        self.assertFalse(FavorTokenDetails.objects.exists())

    def test_award_favor_token_requires_description(self) -> None:
        org = OrganizationFactory()
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="favor_token",
            org_ref=str(org.pk),
        )
        self.assertFalse(result.success)
        self.assertFalse(FavorTokenDetails.objects.exists())

    def test_award_favor_token_rejects_unknown_org(self) -> None:
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="favor_token",
            org_ref="Nonexistent Order",
            description="Cleared the Thornwood ambush",
        )
        self.assertFalse(result.success)
        self.assertFalse(FavorTokenDetails.objects.exists())

    def test_award_favor_token_truncates_long_description(self) -> None:
        """provenance_note is truncated to FavorTokenDetails' max_length=200 before
        create (#2428 whole-branch fix) -- mirrors deliver_mission_money's `[:200]`
        convention. Without the truncation this raises a DB-level DataError instead
        of a clean save."""
        org = OrganizationFactory()
        long_description = "x" * 250

        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="favor_token",
            org_ref=str(org.pk),
            description=long_description,
        )

        self.assertTrue(result.success)
        token = FavorTokenDetails.objects.get(issuing_organization=org)
        self.assertEqual(token.provenance_note, long_description[:200])
        self.assertEqual(len(token.provenance_note), 200)

    def test_award_favor_token_non_gm_is_refused(self) -> None:
        org = OrganizationFactory()
        result = GMAwardAction().run(
            actor=self.player_actor,
            target=self.target,
            award_type="favor_token",
            org_ref=str(org.pk),
            description="Cleared the Thornwood ambush",
        )
        self.assertFalse(result.success)
        self.assertFalse(FavorTokenDetails.objects.exists())


class GMAwardActionStatTests(GMAdjudicationActionsTestBase):
    """``award_type="stat"`` (#3055 slice 1c) -- GM-fiat stat raise + provenance."""

    def setUp(self) -> None:
        super().setUp()
        self.stat_trait = TraitFactory(
            name="adj_award_stat", trait_type=TraitType.STAT, category=TraitCategory.PHYSICAL
        )

    def test_award_stat_raises_by_one_display_dot_with_gm_grant_provenance(self) -> None:
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="stat",
            trait_ref=self.stat_trait.name,
        )
        self.assertTrue(result.success, result.message)
        value = CharacterTraitValue.objects.get(
            character=self.target.sheet_data, trait=self.stat_trait
        ).value
        self.assertEqual(value, STAT_DISPLAY_DIVISOR)

        change = CharacterTraitChange.objects.get(
            character_sheet=self.target.sheet_data, trait=self.stat_trait
        )
        self.assertEqual(change.source, TraitChangeSource.GM_GRANT)
        self.assertEqual(change.old_value, 0)
        self.assertEqual(change.new_value, STAT_DISPLAY_DIVISOR)
        gm_tenure = self.gm_actor.sheet_data.roster_entry.current_tenure
        self.assertEqual(change.granting_tenure, gm_tenure)

    def test_award_stat_rejects_non_stat_trait(self) -> None:
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="stat",
            trait_ref=self.dev_trait.name,
        )
        self.assertFalse(result.success)
        self.assertFalse(CharacterTraitChange.objects.filter(trait=self.dev_trait).exists())

    def test_award_stat_refuses_at_cap(self) -> None:
        # Character level defaults to 1 -> PathStage.PROSPECT; cap it at 3 dots.
        MaturationStatCap.objects.create(path_stage=PathStage.PROSPECT, stat_cap=3)
        CharacterTraitValue.objects.create(
            character=self.target.sheet_data,
            trait=self.stat_trait,
            value=3 * STAT_DISPLAY_DIVISOR,
        )
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="stat",
            trait_ref=self.stat_trait.name,
        )
        self.assertFalse(result.success)
        value = CharacterTraitValue.objects.get(
            character=self.target.sheet_data, trait=self.stat_trait
        ).value
        self.assertEqual(value, 3 * STAT_DISPLAY_DIVISOR)

    def test_award_stat_from_staff_gm_with_no_tenure_still_succeeds(self) -> None:
        """A staff-piloted GM (no roster tenure) still records the grant -- with
        granting_tenure=None."""
        result = GMAwardAction().run(
            actor=self.staff_actor,
            target=self.target,
            award_type="stat",
            trait_ref=self.stat_trait.name,
        )
        self.assertTrue(result.success, result.message)
        change = CharacterTraitChange.objects.get(
            character_sheet=self.target.sheet_data, trait=self.stat_trait
        )
        self.assertIsNone(change.granting_tenure)

    def test_award_stat_requires_trait_ref(self) -> None:
        result = GMAwardAction().run(actor=self.gm_actor, target=self.target, award_type="stat")
        self.assertFalse(result.success)


class GMAwardActionTechniqueTests(GMAdjudicationActionsTestBase):
    """``award_type="technique"`` (#3055 slice 1c) -- GM-fiat technique grant + provenance."""

    def setUp(self) -> None:
        super().setUp()
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.resonance = ResonanceFactory()
        self.gift.resonances.add(self.resonance)
        self.technique = TechniqueFactory(gift=self.gift, name="Adjudication Award Technique")

    def _give_gift(self) -> None:
        CharacterGift.objects.create(character=self.target.sheet_data, gift=self.gift)
        Thread.objects.create(
            owner=self.target.sheet_data,
            resonance=self.resonance,
            target_kind=TargetKind.GIFT,
            target_gift=self.gift,
            level=0,
        )

    def test_award_technique_mints_with_gm_grant_origin_and_announces(self) -> None:
        self._give_gift()
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="technique",
            technique_ref=self.technique.name,
        )
        self.assertTrue(result.success, result.message)
        ct = CharacterTechnique.objects.get(character=self.target.sheet_data)
        self.assertEqual(ct.technique, self.technique)
        self.assertEqual(ct.origin, AcquisitionOrigin.GM_GRANT)

        msg = NarrativeMessage.objects.latest("id")
        self.assertIn(AccessChangeSource.GM_AWARD.label, msg.body)

    def test_award_technique_gift_not_owned_is_refused(self) -> None:
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="technique",
            technique_ref=self.technique.name,
        )
        self.assertFalse(result.success)
        self.assertIn(self.gift.name, result.message)
        self.assertFalse(CharacterTechnique.objects.exists())

    def test_award_technique_already_known_is_refused(self) -> None:
        self._give_gift()
        CharacterTechnique.objects.create(
            character=self.target.sheet_data,
            technique=self.technique,
            origin=AcquisitionOrigin.TRAINED,
        )
        result = GMAwardAction().run(
            actor=self.gm_actor,
            target=self.target,
            award_type="technique",
            technique_ref=self.technique.name,
        )
        self.assertFalse(result.success)
        known_count = CharacterTechnique.objects.filter(character=self.target.sheet_data).count()
        self.assertEqual(known_count, 1)

    def test_award_technique_requires_technique_ref(self) -> None:
        result = GMAwardAction().run(
            actor=self.gm_actor, target=self.target, award_type="technique"
        )
        self.assertFalse(result.success)


class GMApplyConditionActionTests(GMAdjudicationActionsTestBase):
    def test_non_gm_is_refused(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.player_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
        )
        self.assertFalse(result.success)

    def test_junior_floor_enforced(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.starting_gm_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
        )
        self.assertFalse(result.success)
        self.assertIn("Junior GM", result.message)

    def test_staff_bypasses_junior_floor(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.staff_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
        )
        self.assertTrue(result.success)

    def test_apply_condition_creates_instance_with_source_character(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
            note="knocked down by the blast",
        )
        self.assertTrue(result.success)
        instance = ConditionInstance.objects.get(
            target=self.target, condition=self.condition_template
        )
        self.assertEqual(instance.source_character, self.gm_actor)
        self.assertEqual(instance.source_description, "knocked down by the blast")
        self.assertEqual(instance.severity, 1)

    def test_unresolvable_condition_is_refused(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref="No Such Condition",
        )
        self.assertFalse(result.success)

    def test_severity_override_is_honored(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
            severity=3,
        )
        self.assertTrue(result.success)
        instance = ConditionInstance.objects.get(
            target=self.target, condition=self.condition_template
        )
        self.assertEqual(instance.severity, 3)

    def test_non_positive_severity_fails_loud_not_clamped(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
            severity=0,
        )
        self.assertFalse(result.success)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.target, condition=self.condition_template
            ).exists()
        )

    def test_non_positive_duration_fails_loud_not_clamped(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
            duration_rounds=-1,
        )
        self.assertFalse(result.success)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.target, condition=self.condition_template
            ).exists()
        )

    def test_duration_override_is_honored(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
            duration_rounds=7,
        )
        self.assertTrue(result.success)
        instance = ConditionInstance.objects.get(
            target=self.target, condition=self.condition_template
        )
        self.assertEqual(instance.rounds_remaining, 7)

    def test_omitted_duration_uses_template_default(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
        )
        self.assertTrue(result.success)
        instance = ConditionInstance.objects.get(
            target=self.target, condition=self.condition_template
        )
        self.assertEqual(instance.rounds_remaining, self.condition_template.default_duration_value)

    def test_note_is_broadcast_as_a_narrator_outcome_line(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
            note="The wine was poisoned.",
        )
        self.assertTrue(result.success, result.message)
        line = Interaction.objects.get(mode=InteractionMode.OUTCOME)
        self.assertEqual(line.persona.name, NARRATOR_PERSONA_NAME)
        self.assertEqual(line.scene, self.scene)
        presenting = active_persona_for_sheet(self.target.sheet_data).name
        self.assertEqual(
            line.content,
            f"{presenting} is now {self.condition_template.name}. The wine was poisoned.",
        )
        self.assertFalse(line.receivers.exists())

    def test_apply_without_note_broadcasts_nothing(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
        )
        self.assertTrue(result.success, result.message)
        self.assertFalse(Interaction.objects.filter(mode=InteractionMode.OUTCOME).exists())

    def test_hidden_condition_note_reaches_only_the_target(self) -> None:
        hidden = ConditionTemplateFactory(name="Adjudication Marked", is_visible_to_others=False)
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref=hidden.name,
            note="A brand only you can feel.",
        )
        self.assertTrue(result.success, result.message)
        line = Interaction.objects.get(mode=InteractionMode.OUTCOME)
        receiver_ids = list(line.receivers.values_list("persona_id", flat=True))
        self.assertEqual(receiver_ids, [active_persona_for_sheet(self.target.sheet_data).pk])
        presenting = active_persona_for_sheet(self.target.sheet_data).name
        self.assertEqual(
            line.content,
            f"{presenting} is now Adjudication Marked. A brand only you can feel.",
        )

    def test_note_reaches_room_telnet_clients(self) -> None:
        with mock.patch.object(self.room, "msg_contents") as msg_contents:
            GMApplyConditionAction().run(
                actor=self.gm_actor,
                target=self.target,
                condition_ref=self.condition_template.name,
                note="The wine was poisoned.",
            )
        presenting = active_persona_for_sheet(self.target.sheet_data).name
        msg_contents.assert_called_once_with(
            f"{presenting} is now {self.condition_template.name}. The wine was poisoned."
        )

    def test_hidden_condition_note_is_not_sent_to_the_room(self) -> None:
        hidden = ConditionTemplateFactory(name="Adjudication Marked", is_visible_to_others=False)
        with (
            mock.patch.object(self.room, "msg_contents") as msg_contents,
            mock.patch.object(self.target, "msg") as target_msg,
        ):
            GMApplyConditionAction().run(
                actor=self.gm_actor,
                target=self.target,
                condition_ref=hidden.name,
                note="A brand only you can feel.",
            )
        presenting = active_persona_for_sheet(self.target.sheet_data).name
        msg_contents.assert_not_called()
        target_msg.assert_called_once_with(
            f"{presenting} is now Adjudication Marked. A brand only you can feel."
        )

    def test_visible_condition_note_reaches_target_when_gm_actor_has_no_location(self) -> None:
        # Uses self.staff_actor, not self.gm_actor: IsSceneGMPrerequisite resolves the
        # acting GM's scene via ``get_active_scene(actor.location)``, so a GM with no
        # location can never pass it. Staff bypasses that check via is_staff_observer
        # regardless of location, which is the only way to reach this helper with an
        # unlocated actor.
        self.staff_actor.location = None
        self.staff_actor.save()
        with mock.patch.object(self.target, "msg") as target_msg:
            result = GMApplyConditionAction().run(
                actor=self.staff_actor,
                target=self.target,
                condition_ref=self.condition_template.name,
                note="The wine was poisoned.",
            )
        self.assertTrue(result.success, result.message)
        presenting = active_persona_for_sheet(self.target.sheet_data).name
        expected = f"{presenting} is now {self.condition_template.name}. The wine was poisoned."
        target_msg.assert_called_once_with(expected)
        line = Interaction.objects.get(mode=InteractionMode.OUTCOME)
        self.assertIsNone(line.scene)

    def test_visible_condition_on_sheetless_target_is_named_by_key(self) -> None:
        vase = ObjectDBFactory(db_key="Adjudication Vase", location=self.room)
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=vase,
            condition_ref=self.condition_template.name,
            note="It was cracked in the fall.",
        )
        self.assertTrue(result.success, result.message)
        line = Interaction.objects.get(mode=InteractionMode.OUTCOME)
        self.assertEqual(
            line.content,
            f"Adjudication Vase is now {self.condition_template.name}. It was cracked in the fall.",
        )

    def test_hidden_condition_on_sheetless_target_records_nothing(self) -> None:
        hidden = ConditionTemplateFactory(name="Adjudication Marked", is_visible_to_others=False)
        vase = ObjectDBFactory(db_key="Adjudication Vase", location=self.room)
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=vase,
            condition_ref=hidden.name,
            note="It was cracked in the fall.",
        )
        self.assertTrue(result.success, result.message)
        self.assertFalse(Interaction.objects.filter(mode=InteractionMode.OUTCOME).exists())


class GMRemoveConditionActionTests(GMAdjudicationActionsTestBase):
    """``gm_remove_condition`` (#3431) -- the referee off-switch ``GMApplyConditionAction``
    never got. Mirrors ``GMApplyConditionActionTests``'s permission-journey shape."""

    def _apply(self) -> None:
        result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
        )
        assert result.success, result.message

    def test_non_gm_is_refused(self) -> None:
        self._apply()
        result = GMRemoveConditionAction().run(
            actor=self.player_actor,
            target=self.target,
            condition=self.condition_template.name,
            reason="scene wrapped up",
        )
        self.assertFalse(result.success)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.target, condition=self.condition_template
            ).exists()
        )

    def test_junior_floor_enforced(self) -> None:
        self._apply()
        result = GMRemoveConditionAction().run(
            actor=self.starting_gm_actor,
            target=self.target,
            condition=self.condition_template.name,
            reason="scene wrapped up",
        )
        self.assertFalse(result.success)
        self.assertIn("Junior GM", result.message)

    def test_staff_bypasses_junior_floor(self) -> None:
        self._apply()
        result = GMRemoveConditionAction().run(
            actor=self.staff_actor,
            target=self.target,
            condition=self.condition_template.name,
            reason="scene wrapped up",
        )
        self.assertTrue(result.success, result.message)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.target, condition=self.condition_template
            ).exists()
        )

    def test_removes_active_instance_and_echoes_reason(self) -> None:
        self._apply()
        result = GMRemoveConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition=self.condition_template.name,
            reason="the consequence served its purpose",
        )
        self.assertTrue(result.success, result.message)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.target, condition=self.condition_template
            ).exists()
        )
        self.assertIn("the consequence served its purpose", result.message)

    def test_reason_is_required(self) -> None:
        self._apply()
        result = GMRemoveConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition=self.condition_template.name,
        )
        self.assertFalse(result.success)
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.target, condition=self.condition_template
            ).exists()
        )

    def test_target_without_the_condition_is_refused(self) -> None:
        """Catalog-bounded to ACTIVE instances -- refuses rather than silently
        no-opping like ``remove_condition_by_name`` (#3431)."""
        result = GMRemoveConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition=self.condition_template.name,
            reason="never applied",
        )
        self.assertFalse(result.success)
        self.assertIn(self.condition_template.name, result.message)

    def test_unknown_condition_name_is_refused(self) -> None:
        self._apply()
        result = GMRemoveConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition="No Such Condition",
            reason="scene wrapped up",
        )
        self.assertFalse(result.success)

    def test_rest_target_resolution_accepts_int_pk(self) -> None:
        """See ``RESTTargetResolutionTests`` -- the REST dispatch path sends a
        plain int, resolved by ``_resolve_gm_target`` (#3431)."""
        self._apply()
        result = GMRemoveConditionAction().run(
            actor=self.gm_actor,
            target=self.target.pk,
            condition=self.condition_template.name,
            reason="scene wrapped up",
        )
        self.assertTrue(result.success, result.message)


class GMListConditionsActionTests(GMAdjudicationActionsTestBase):
    """``gm_list_conditions`` (#3431) -- feeds the web Remove-Condition picker; no
    ViewSet read exposes a target's hidden active conditions to their GM."""

    def test_non_gm_is_refused(self) -> None:
        result = GMListConditionsAction().run(actor=self.player_actor, target=self.target)
        self.assertFalse(result.success)

    def test_junior_floor_enforced(self) -> None:
        result = GMListConditionsAction().run(actor=self.starting_gm_actor, target=self.target)
        self.assertFalse(result.success)
        self.assertIn("Junior GM", result.message)

    def test_lists_active_instance_with_template_name_severity_and_duration(self) -> None:
        apply_result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
            severity=2,
            duration_rounds=5,
        )
        assert apply_result.success, apply_result.message

        result = GMListConditionsAction().run(actor=self.gm_actor, target=self.target)
        self.assertTrue(result.success, result.message)
        rows = result.data["conditions"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["name"], self.condition_template.name)
        self.assertEqual(row["severity"], 2)
        self.assertEqual(row["rounds_remaining"], 5)

    def test_empty_when_target_has_no_active_conditions(self) -> None:
        result = GMListConditionsAction().run(actor=self.gm_actor, target=self.target)
        self.assertTrue(result.success)
        self.assertEqual(result.data["conditions"], [])


class GMRemoveConditionActionJourneyTests(GMAdjudicationActionsTestBase):
    """End-to-end: GM applies, then lists, then removes a condition on a scene
    participant -- the #3431 spec's headline test seam."""

    def test_apply_then_list_then_remove_journey(self) -> None:
        apply_result = GMApplyConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition_ref=self.condition_template.name,
        )
        self.assertTrue(apply_result.success, apply_result.message)

        list_result = GMListConditionsAction().run(actor=self.gm_actor, target=self.target)
        self.assertTrue(list_result.success)
        self.assertEqual(len(list_result.data["conditions"]), 1)
        self.assertEqual(list_result.data["conditions"][0]["name"], self.condition_template.name)

        remove_result = GMRemoveConditionAction().run(
            actor=self.gm_actor,
            target=self.target,
            condition=self.condition_template.name,
            reason="the scene's over",
        )
        self.assertTrue(remove_result.success, remove_result.message)
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.target, condition=self.condition_template
            ).exists()
        )

        final_list = GMListConditionsAction().run(actor=self.gm_actor, target=self.target)
        self.assertEqual(final_list.data["conditions"], [])
