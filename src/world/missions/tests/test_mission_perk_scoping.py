"""E2E test: ``situation_ctx`` threading at the mission check call sites (#2536 slice 3).

Task 1 built ``SituationContext(mission=...)`` plus mission-category/template scope
matching inside ``world.checks.services._situational_perk_check_bonus``
(``world.covenants.perks.services.perk_scope_matches``). Task 2 (this file's subject)
threads ``situation_ctx=SituationContext(..., mission=instance)`` into the six mission
``perform_check`` call sites so a Court-flavored ``CHECK_BONUS`` situational perk scoped
to a ``MissionCategory`` can actually fire on a mission check.

Drives the real ``resolve_option`` service call site (not just the
``_compute_check_breakdown`` arithmetic helper) — the check's real ``total_points`` is
captured by wrapping ``perform_check`` so the assertion proves the wiring end to end, not
just the isolated scoping arithmetic (already covered by
``world.checks.tests.test_situational_perk_check_bonus``).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.services import _compute_check_breakdown, perform_check
from world.checks.test_helpers import force_check_outcome
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind
from world.magic.factories import ThreadFactory
from world.missions.constants import OptionKind, OptionSource
from world.missions.factories import (
    MissionCategoryFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionOptionRouteFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.services import resolve_option
from world.traits.factories import CheckOutcomeFactory

_PERFORM_CHECK = "world.missions.services.resolution.perform_check"
_EXPECTED_BONUS = 10  # magnitude_tenths=10 * thread level=10 / 10 == 10


class MissionCheckSituationCtxScopingTests(TestCase):
    """``resolve_option`` threads ``situation_ctx(mission=instance)`` into perform_check.

    Not ``setUpTestData`` — factories create Evennia ``ObjectDB`` instances (``DbHolder``,
    not deepcopyable), same rationale as the sibling ``test_situational_perk_check_bonus``
    suite this mirrors.
    """

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.check_type = CheckTypeFactory(name="CourtScopeSneak")
        self.success = CheckOutcomeFactory(name="CourtScopeSuccess", success_level=3)

        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(),
            covenant_role=role,
            engaged=True,
        )
        self.category = MissionCategoryFactory()
        VowSituationalPerkFactory(
            covenant_role=role,
            beneficiary=PerkBeneficiary.SELF,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            magnitude_tenths=10,
            check_type=None,
            mission_category=self.category,
        )
        ThreadFactory(owner=self.sheet, level=10)

    def _build_run(self, *, matching_category: bool):
        template = MissionTemplateFactory(risk_tier=1)
        template.categories.add(self.category if matching_category else MissionCategoryFactory())
        instance = MissionInstanceFactory(template=template)
        entry = MissionNodeFactory(template=template, key="entry", is_entry=True)
        option = MissionOptionFactory(
            node=entry,
            order=0,
            option_kind=OptionKind.CHECK,
            source_kind=OptionSource.AUTHORED,
            authored_check_type=self.check_type,
        )
        MissionOptionRouteFactory(option=option, outcome_tier=self.success, target_node=None)
        actor = MissionParticipantFactory(
            instance=instance, character=self.character, is_contract_holder=True
        )
        return instance, entry, option, actor

    def _resolve_and_capture_total_points(self, instance, entry, option, actor) -> int:
        captured: list[int] = []

        def _spy(*args, **kwargs):
            result = perform_check(*args, **kwargs)
            captured.append(result.total_points)
            return result

        with force_check_outcome(self.success), patch(_PERFORM_CHECK, side_effect=_spy):
            resolve_option(instance, entry, option, actor)
        return captured[0]

    def _baseline_total_points(self) -> int:
        """``total_points`` with no situation_ctx at all — the perk-free control."""
        return _compute_check_breakdown(
            self.character,
            self.check_type,
            target_difficulty=0,
            extra_modifiers=0,
            effort_level=None,
            fatigue_penalty=0,
            specialization=None,
            situation_ctx=None,
        ).total_points

    def test_matching_category_template_fires_the_perk(self) -> None:
        instance, entry, option, actor = self._build_run(matching_category=True)
        total = self._resolve_and_capture_total_points(instance, entry, option, actor)
        self.assertEqual(total, self._baseline_total_points() + _EXPECTED_BONUS)

    def test_non_matching_category_template_does_not_fire_the_perk(self) -> None:
        instance, entry, option, actor = self._build_run(matching_category=False)
        total = self._resolve_and_capture_total_points(instance, entry, option, actor)
        self.assertEqual(total, self._baseline_total_points())
