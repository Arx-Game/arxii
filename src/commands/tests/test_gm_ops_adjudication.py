"""Telnet tests for the GM adjudication toolkit subverbs (#2118).

``gm check`` / ``gm award`` / ``gm condition`` on ``CmdGMDashboard`` --
thin parsing + ``action.run()`` over ``InvokeCatalogCheckAction`` /
``GMAwardAction`` / ``GMApplyConditionAction``. These tests exercise the
telnet-layer grammar (usage errors, subverb routing); the full permission
matrix and catalog-only invariant are covered by
``actions/tests/test_gm_adjudication_actions.py``.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from commands.gm_ops import CmdGMDashboard
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance
from world.currency.models import FavorTokenDetails
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.progression.models import ExperiencePointsData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.societies.factories import OrganizationFactory
from world.traits.factories import CheckSystemSetupFactory, TraitFactory
from world.traits.models import (
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    ResultChart,
    Trait,
    TraitCategory,
    TraitType,
)


def _room(*, db_key: str = "GMOpsRoom") -> object:
    return ObjectDBFactory(db_key=db_key, db_typeclass_path="typeclasses.rooms.Room")


def _pc_in_room(room: object, *, db_key: str) -> tuple[object, object]:
    char = CharacterFactory(db_key=db_key, location=room)
    CharacterSheetFactory(character=char)
    entry = RosterEntryFactory(character_sheet__character=char)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    return char, tenure.player_data.account


def _run_cmd(caller: object, args: str) -> list[str]:
    cmd = CmdGMDashboard()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"gm {args}".strip()
    cmd.func()
    return [str(c.args[0]) for c in caller.msg.call_args_list if c.args]


class GMOpsAdjudicationTestBase(TestCase):
    """Room + scene + JUNIOR-tier scene-GM caller + target + a check/condition catalog."""

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
            (0, 0, "GMOpsNone"),
            (1, 10, "GMOpsNovice"),
            (2, 25, "GMOpsCompetent"),
            (3, 50, "GMOpsExpert"),
        ]:
            CheckRank.objects.get_or_create(
                rank=rank_val, defaults={"min_points": min_pts, "name": name}
            )

        self.room = _room()
        self.scene = SceneFactory(location=self.room)

        self.gm_actor, self.gm_account = _pc_in_room(self.room, db_key="GMOpsGM")
        GMProfileFactory(account=self.gm_account, level=GMLevel.JUNIOR)
        SceneParticipationFactory(scene=self.scene, account=self.gm_account, is_gm=True)
        self.gm_actor.msg = MagicMock()

        self.player_actor, self.player_account = _pc_in_room(self.room, db_key="GMOpsPlayer")
        SceneParticipationFactory(scene=self.scene, account=self.player_account, is_gm=False)
        self.player_actor.msg = MagicMock()

        self.target, self.target_account = _pc_in_room(self.room, db_key="GMOpsTarget")

        self.check_trait, _ = Trait.objects.get_or_create(
            name="gmops_check_strength",
            defaults={"trait_type": TraitType.STAT, "category": TraitCategory.PHYSICAL},
        )
        self.check_category = CheckCategoryFactory(name="gmops_check_combat")
        self.check_type = CheckTypeFactory(name="Grapple", category=self.check_category)
        CheckTypeTraitFactory(
            check_type=self.check_type, trait=self.check_trait, weight=Decimal("1.0")
        )
        CharacterTraitValue.objects.get_or_create(
            character=self.target.sheet_data, trait=self.check_trait, defaults={"value": 30}
        )

        self.dev_trait = TraitFactory(name="gmops_dev_skill", trait_type=TraitType.SKILL)
        self.condition_template = ConditionTemplateFactory(name="GMOps Winded")


class CmdGMCheckTests(GMOpsAdjudicationTestBase):
    def test_bare_check_lists_catalog(self) -> None:
        messages = _run_cmd(self.gm_actor, "check")
        self.assertTrue(any(self.check_type.name in m for m in messages))

    def test_check_find_with_term(self) -> None:
        messages = _run_cmd(self.gm_actor, "check find Grapple")
        self.assertTrue(any(self.check_type.name in m for m in messages))

    def test_check_invoke_resolves_and_messages_caller(self) -> None:
        messages = _run_cmd(self.gm_actor, f"check {self.target.key} {self.check_type.name}=hard")
        self.assertTrue(messages)
        self.assertTrue(any(self.check_type.name in m for m in messages))

    def test_check_invoke_with_edge_reason(self) -> None:
        messages = _run_cmd(
            self.gm_actor,
            f"check {self.target.key} {self.check_type.name}=hard edge=ally braces the door",
        )
        joined = " ".join(messages)
        self.assertIn("edge", joined)
        self.assertIn("ally braces the door", joined)

    def test_check_missing_band_shows_usage(self) -> None:
        messages = _run_cmd(self.gm_actor, f"check {self.target.key} justatoken")
        self.assertTrue(any("Usage: gm check" in m for m in messages))

    def test_check_unknown_target_reports_not_found(self) -> None:
        messages = _run_cmd(self.gm_actor, f"check NoSuchCharacter {self.check_type.name}=hard")
        self.assertTrue(any("here" in m.lower() or "no character" in m.lower() for m in messages))

    def test_non_gm_is_refused(self) -> None:
        messages = _run_cmd(
            self.player_actor, f"check {self.target.key} {self.check_type.name}=hard"
        )
        self.assertTrue(any("scene's GM or staff" in m for m in messages))


class CmdGMAwardTests(GMOpsAdjudicationTestBase):
    def test_award_xp(self) -> None:
        messages = _run_cmd(self.gm_actor, f"award {self.target.key} xp=20 reason=good pose")
        self.assertTrue(any("20" in m and "XP" in m for m in messages))
        xp_data = ExperiencePointsData.objects.get(account=self.target_account)
        self.assertEqual(xp_data.total_earned, 20)

    def test_award_development(self) -> None:
        messages = _run_cmd(
            self.gm_actor,
            f"award {self.target.key} dev={self.dev_trait.name} amount=4",
        )
        self.assertTrue(messages)
        self.assertFalse(any("Usage" in m for m in messages))

    def test_award_missing_type_shows_usage(self) -> None:
        messages = _run_cmd(self.gm_actor, f"award {self.target.key} amount=5")
        self.assertTrue(any("Usage: gm award" in m for m in messages))

    def test_non_gm_is_refused(self) -> None:
        messages = _run_cmd(self.player_actor, f"award {self.target.key} xp=20")
        self.assertTrue(len(messages) > 0)
        self.assertFalse(ExperiencePointsData.objects.filter(account=self.target_account).exists())

    def test_award_favor_token_mints_golden_hare(self) -> None:
        org = OrganizationFactory(name="GMOps Academy")
        messages = _run_cmd(
            self.gm_actor,
            f"award {self.target.key} hare=GMOps Academy reason=Cleared the Thornwood ambush",
        )
        self.assertTrue(any("Golden Hare" in m for m in messages))
        token = FavorTokenDetails.objects.get(issuing_organization=org)
        self.assertEqual(token.provenance_note, "Cleared the Thornwood ambush")

    def test_award_favor_token_non_gm_is_refused(self) -> None:
        OrganizationFactory(name="GMOps Academy")
        messages = _run_cmd(
            self.player_actor,
            f"award {self.target.key} hare=GMOps Academy reason=Cleared the Thornwood ambush",
        )
        self.assertTrue(len(messages) > 0)
        self.assertFalse(FavorTokenDetails.objects.exists())


class CmdGMConditionTests(GMOpsAdjudicationTestBase):
    def test_apply_condition(self) -> None:
        messages = _run_cmd(
            self.gm_actor,
            f"condition {self.target.key} condition={self.condition_template.name}"
            " note=knocked flat",
        )
        self.assertTrue(any(self.condition_template.name in m for m in messages))
        self.assertTrue(
            ConditionInstance.objects.filter(
                target=self.target, condition=self.condition_template
            ).exists()
        )

    def test_condition_missing_condition_key_shows_usage(self) -> None:
        messages = _run_cmd(self.gm_actor, f"condition {self.target.key} severity=2")
        self.assertTrue(any("Usage: gm condition" in m for m in messages))

    def test_non_gm_is_refused(self) -> None:
        messages = _run_cmd(
            self.player_actor,
            f"condition {self.target.key} condition={self.condition_template.name}",
        )
        self.assertFalse(
            ConditionInstance.objects.filter(
                target=self.target, condition=self.condition_template
            ).exists()
        )
        self.assertTrue(len(messages) > 0)
