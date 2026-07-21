"""Tests for CHECK_BONUS situational-perk threading into ``perform_check`` (#2536, Task 5).

``perform_check`` gains a keyword-only ``situation_ctx`` (a ``SituationContext``,
``world.covenants.perks.context``) that — when provided — fires ``CHECK_BONUS``
perks (``world.covenants.perks.services.applicable_perks``) scoped to the check's
``CheckType`` (or scope-less perks) and folds their thread-level-scaled magnitude
into the same total ``extra_modifiers`` feeds. ``situation_ctx=None`` (the default,
every pre-#2536 call site) is byte-identical — no query, no perk lookup — which is
also why the existing checks suite passes UNMODIFIED (the primary proof; this file
covers the opt-in behavior directly).

Uses ``_compute_check_breakdown`` (already a direct-import test target in
``test_services.py``) for exact-arithmetic assertions — sidesteps the dice roll
entirely, mirroring how ``test_services.py`` tests ``_calculate_capability_points``.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.battles.constants import BattleActionKind
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.services import _compute_check_breakdown, perform_check
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind
from world.covenants.perks.context import SituationContext
from world.magic.factories import ThreadFactory
from world.missions.factories import (
    MissionCategoryFactory,
    MissionInstanceFactory,
    MissionTemplateFactory,
)


class SituationalPerkCheckBonusTests(TestCase):
    """Not ``setUpTestData`` — factories create Evennia ``ObjectDB`` instances
    (``DbHolder``, not deepcopyable), same rationale as the perk resolution /
    power-term suites."""

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.check_type = CheckTypeFactory(name="Perception")

    def _engage_role(self, *, sheet=None, engaged=True, covenant=None, role=None):
        role = role or CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=sheet or self.sheet,
            covenant=covenant or CovenantFactory(),
            covenant_role=role,
            engaged=engaged,
        )
        return role

    def _breakdown_total(self, check_type, *, situation_ctx):
        breakdown = _compute_check_breakdown(
            self.character,
            check_type,
            target_difficulty=0,
            extra_modifiers=0,
            effort_level=None,
            fatigue_penalty=0,
            specialization=None,
            situation_ctx=situation_ctx,
        )
        return breakdown.total_points

    def test_situation_ctx_none_is_byte_identical(self) -> None:
        """A matching, unscoped CHECK_BONUS perk exists, but situation_ctx=None
        means it never fires — total_points is unaffected (default behavior)."""
        role = self._engage_role()
        VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=50,
            check_type=None,
        )
        ThreadFactory(owner=self.sheet, level=10)

        self.assertEqual(self._breakdown_total(self.check_type, situation_ctx=None), 0)

    def test_null_scope_perk_fires_on_any_check(self) -> None:
        """check_type=None on the perk row -> fires regardless of which
        CheckType is being rolled. 8 * 15 / 10 = 12.0 -> 12."""
        role = self._engage_role()
        VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=15,
            check_type=None,
        )
        ThreadFactory(owner=self.sheet, level=8)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        other_check_type = CheckTypeFactory(name="Stealth")
        self.assertEqual(self._breakdown_total(self.check_type, situation_ctx=ctx), 12)
        self.assertEqual(self._breakdown_total(other_check_type, situation_ctx=ctx), 12)

    def test_scoped_perk_fires_only_on_matching_check_type(self) -> None:
        """A perk scoped to a specific CheckType fires only for THAT check —
        a different CheckType gets 0. 6 * 20 / 10 = 12.0 -> 12."""
        role = self._engage_role()
        VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=20,
            check_type=self.check_type,
        )
        ThreadFactory(owner=self.sheet, level=6)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        other_check_type = CheckTypeFactory(name="Stealth")
        self.assertEqual(self._breakdown_total(self.check_type, situation_ctx=ctx), 12)
        self.assertEqual(self._breakdown_total(other_check_type, situation_ctx=ctx), 0)

    def test_mission_category_scope_requires_matching_mission(self) -> None:
        """#2536 slice 3 Court scoping: a mission_category-scoped perk never
        fires when situation_ctx.mission is None, and fires when the ctx
        carries a MissionInstance whose template carries that category.
        10 * 10 / 10 = 10."""
        role = self._engage_role()
        category = MissionCategoryFactory()
        VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=10,
            check_type=None,
            mission_category=category,
        )
        ThreadFactory(owner=self.sheet, level=10)

        ctx_no_mission = SituationContext(
            holder=self.sheet, subject=self.sheet, target=None, resolution=None
        )
        self.assertEqual(self._breakdown_total(self.check_type, situation_ctx=ctx_no_mission), 0)

        template = MissionTemplateFactory()
        template.categories.add(category)
        instance = MissionInstanceFactory(template=template)
        ctx_with_mission = SituationContext(
            holder=self.sheet, subject=self.sheet, target=None, resolution=None, mission=instance
        )
        self.assertEqual(self._breakdown_total(self.check_type, situation_ctx=ctx_with_mission), 10)

    def test_mission_category_scope_does_not_fire_for_non_matching_category(self) -> None:
        """A mission with a DIFFERENT category than the perk's scope stays silent."""
        role = self._engage_role()
        category = MissionCategoryFactory()
        other_category = MissionCategoryFactory()
        VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=10,
            check_type=None,
            mission_category=category,
        )
        ThreadFactory(owner=self.sheet, level=10)

        template = MissionTemplateFactory()
        template.categories.add(other_category)
        instance = MissionInstanceFactory(template=template)
        ctx = SituationContext(
            holder=self.sheet, subject=self.sheet, target=None, resolution=None, mission=instance
        )
        self.assertEqual(self._breakdown_total(self.check_type, situation_ctx=ctx), 0)

    def test_battle_action_kind_scope_matches_exact_kind(self) -> None:
        """#2536 slice 3 Battle scoping: a battle_action_kind=ROUT perk fires
        only when situation_ctx.battle_action_kind == 'rout'. 10 * 10 / 10 = 10."""
        role = self._engage_role()
        VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=10,
            check_type=None,
            battle_action_kind=BattleActionKind.ROUT,
        )
        ThreadFactory(owner=self.sheet, level=10)

        ctx_no_kind = SituationContext(
            holder=self.sheet, subject=self.sheet, target=None, resolution=None
        )
        self.assertEqual(self._breakdown_total(self.check_type, situation_ctx=ctx_no_kind), 0)

        ctx_wrong_kind = SituationContext(
            holder=self.sheet,
            subject=self.sheet,
            target=None,
            resolution=None,
            battle_action_kind=BattleActionKind.RALLY,
        )
        self.assertEqual(self._breakdown_total(self.check_type, situation_ctx=ctx_wrong_kind), 0)

        ctx_matching_kind = SituationContext(
            holder=self.sheet,
            subject=self.sheet,
            target=None,
            resolution=None,
            battle_action_kind=BattleActionKind.ROUT,
        )
        self.assertEqual(
            self._breakdown_total(self.check_type, situation_ctx=ctx_matching_kind), 10
        )

    def test_ally_beneficiary_check_bonus_fires_for_covenant_mate(self) -> None:
        """A COVENANT_ALLIES CHECK_BONUS perk held by a co-present covenant-mate,
        co-present via an active Scene, fires on the SUBJECT's check (scaled by
        the SUBJECT's own thread level, not the mate's)."""
        from evennia import create_object

        from world.scenes.factories import SceneFactory

        room = create_object("typeclasses.rooms.Room", key="CheckPerkAllyRoom", nohome=True)
        self.character.location = room
        self.character.save()
        SceneFactory(location=room)

        mate_character = CharacterFactory()
        mate_sheet = CharacterSheetFactory(character=mate_character)
        mate_character.location = room
        mate_character.save()

        covenant = CovenantFactory()
        mate_role = CovenantRoleFactory(covenant_type=covenant.covenant_type)
        subject_role = CovenantRoleFactory(covenant_type=covenant.covenant_type)

        # Subject needs SOME engaged role (in this covenant) before an ally's
        # perk can reach them at all — see applicable_perks' _ally_candidates.
        self._engage_role(sheet=self.sheet, covenant=covenant, role=subject_role)
        CharacterCovenantRoleFactory(
            character_sheet=mate_sheet, covenant=covenant, covenant_role=mate_role, engaged=True
        )

        VowSituationalPerkFactory(
            covenant_role=mate_role,
            beneficiary=PerkBeneficiary.COVENANT_ALLIES,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=10,
            check_type=None,
        )

        ThreadFactory(owner=self.sheet, level=6)  # subject's own thread level, not the mate's

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        # 6 * 10 / 10 = 6 -- proves the mate's COVENANT_ALLIES perk fired for the subject
        self.assertEqual(self._breakdown_total(self.check_type, situation_ctx=ctx), 6)

    def test_perform_check_integration_folds_perk_bonus_into_total_points(self) -> None:
        """End-to-end through the public perform_check() API (not the private
        breakdown helper): CheckResult.total_points reflects the fired perk's
        contribution exactly, with a fixed die so the roll itself is inert to
        the assertion."""
        from unittest.mock import patch

        role = self._engage_role()
        VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=10,
            check_type=self.check_type,
        )
        ThreadFactory(owner=self.sheet, level=4)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with patch("world.checks.services.random.randint", return_value=50):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)
        # 4 * 10 / 10 = 4
        self.assertEqual(result.total_points, 4)

    def test_fired_perk_announced_exactly_once(self) -> None:
        """Wiring + no-double-announce proof (#2536 Task 6): one
        ``_compute_check_breakdown`` call fires one CHECK_BONUS perk and
        calls ``announce_fired_perks`` exactly once with exactly that one
        scoped firing — ``_situational_perk_check_bonus`` computes its
        breakdown exactly once per ``perform_check`` call (normal-roll and
        forced-outcome branches are mutually exclusive), so the announce
        call site inside it cannot double-announce."""
        from unittest.mock import patch

        from evennia import create_object

        room = create_object("typeclasses.rooms.Room", key="CheckPerkAnnounceRoom", nohome=True)
        self.character.location = room
        self.character.save()

        role = self._engage_role()
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=10,
            check_type=self.check_type,
        )
        ThreadFactory(owner=self.sheet, level=4)

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with (
            patch("world.checks.services.random.randint", return_value=50),
            patch("world.covenants.perks.services.announce_fired_perks") as mock_announce,
        ):
            perform_check(self.character, self.check_type, situation_ctx=ctx)

        assert mock_announce.call_count == 1
        (fired_arg,), kwargs = mock_announce.call_args
        assert len(fired_arg) == 1
        assert fired_arg[0].perk == perk
        assert kwargs["subject"] == self.sheet
        assert kwargs["location"] == room
