"""Tests for dormant-vow messaging — the loud OFF state (#2536 slice 3, Task 7,
ruling 2).

A DISENGAGED-but-active covenant role never buffs its holder (ruling 1's
stark-power rule, untouched), but slice 3's ruling 2 says that silence must
be LOUD: the exact moment a disengaged perk's situations would have held, the
holder is told so directly — ``"your vow lies dormant — {perk.name} would
have answered here"`` — HOLDER-only, never the room.

``perks.services.dormant_perk_firings`` is the enumeration half (the inverted
mirror of ``_self_candidates``'s engaged-only filter, plus the Task-1 scope
filter baked in); ``announce_dormant_perks`` is the delivery half. Three
wiring seams (``checks.services._situational_perk_check_bonus`` /
``_apply_outcome_guarantees``, ``magic.services.power_terms
.vow_situational_power_term``) each make one dormant pass right after their
own live ``applicable_perks`` call.

Not ``setUpTestData`` — factories here create Evennia ``ObjectDB`` instances
(``DbHolder``, not deepcopyable), same rationale as the other perk suites
(``test_perk_resolution.py``, ``test_perk_announce.py``).
"""

from __future__ import annotations

from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from evennia_extensions.factories import CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.services import perform_check
from world.checks.test_helpers import force_check_outcome
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
    VowSituationalPerkFactory,
)
from world.covenants.perks.constants import PerkBeneficiary, PerkEffectKind
from world.covenants.perks.context import SituationContext
from world.covenants.perks.services import (
    FiredPerk,
    announce_dormant_perks,
    applicable_perks,
    dormant_perk_firings,
)
from world.magic.factories import TechniqueFactory
from world.magic.services.power_terms import PowerTermContext, vow_situational_power_term
from world.missions.factories import (
    MissionCategoryFactory,
    MissionInstanceFactory,
    MissionTemplateFactory,
)
from world.traits.factories import (
    CheckOutcomeFactory,
    ResultChartFactory,
    ResultChartOutcomeFactory,
)
from world.traits.models import ResultChart


class DormantPerkFiringsTests(TestCase):
    """Direct unit tests on ``dormant_perk_firings``'s enumeration contract."""

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)

    def _membership(self, *, engaged: bool) -> None:
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            engaged=engaged,
        )

    def test_disengaged_membership_with_holding_situation_is_dormant(self) -> None:
        """A disengaged-but-active role with an unscoped perk (no attached
        situations -- trivially "holds") is a dormant candidate."""
        self._membership(engaged=False)
        perk = VowSituationalPerkFactory(
            covenant_role=self.role,
            effect_kind=PerkEffectKind.POWER_BONUS,
            beneficiary=PerkBeneficiary.SELF,
        )

        dormant = dormant_perk_firings(
            self.sheet, effect_kind=PerkEffectKind.POWER_BONUS, resolution=None, target=None
        )

        assert len(dormant) == 1
        assert dormant[0].perk == perk

    def test_engaged_membership_never_dormant(self) -> None:
        """(b) An engaged role never shows up as dormant -- it actually fires
        live instead."""
        self._membership(engaged=True)
        VowSituationalPerkFactory(
            covenant_role=self.role,
            effect_kind=PerkEffectKind.POWER_BONUS,
            beneficiary=PerkBeneficiary.SELF,
        )

        live = applicable_perks(
            self.sheet, effect_kind=PerkEffectKind.POWER_BONUS, resolution=None, target=None
        )
        dormant = dormant_perk_firings(
            self.sheet, effect_kind=PerkEffectKind.POWER_BONUS, resolution=None, target=None
        )

        assert len(live) == 1
        assert dormant == []

    def test_no_disengaged_membership_costs_zero_extra_queries(self) -> None:
        """(c) With only an ENGAGED membership (no disengaged one at all),
        adding the dormant pass right after the live ``applicable_perks``
        call costs nothing beyond the live-only baseline -- the cached
        ``covenant_roles`` handler list answers ``dormant_perk_firings``
        without a query of its own."""
        self._membership(engaged=True)
        VowSituationalPerkFactory(
            covenant_role=self.role,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            beneficiary=PerkBeneficiary.SELF,
        )

        def _live_only() -> None:
            applicable_perks(
                self.sheet, effect_kind=PerkEffectKind.CHECK_BONUS, resolution=None, target=None
            )

        # Warm every cache (the covenant-roles handler in particular) before
        # either measurement, so both captures start from the same warm
        # state -- mirrors PerkResolutionQueryBudgetTests' warm-up rationale
        # in test_perk_resolution.py.
        _live_only()

        with CaptureQueriesContext(connection) as baseline:
            _live_only()

        with CaptureQueriesContext(connection) as with_dormant_pass:
            applicable_perks(
                self.sheet, effect_kind=PerkEffectKind.CHECK_BONUS, resolution=None, target=None
            )
            dormant_perk_firings(
                self.sheet, effect_kind=PerkEffectKind.CHECK_BONUS, resolution=None, target=None
            )

        self.assertEqual(len(with_dormant_pass.captured_queries), len(baseline.captured_queries))

    def test_mission_scoped_dormant_perk_silent_off_mission(self) -> None:
        """(e) A mission-category-scoped dormant perk stays silent when the
        resolution carries no MissionInstance, and fires once one carrying
        the matching category is threaded through."""
        self._membership(engaged=False)
        category = MissionCategoryFactory()
        perk = VowSituationalPerkFactory(
            covenant_role=self.role,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            beneficiary=PerkBeneficiary.SELF,
            check_type=None,
            mission_category=category,
        )

        off_mission = dormant_perk_firings(
            self.sheet,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            resolution=None,
            target=None,
            mission=None,
        )
        assert off_mission == []

        template = MissionTemplateFactory()
        template.categories.add(category)
        instance = MissionInstanceFactory(template=template)
        on_mission = dormant_perk_firings(
            self.sheet,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            resolution=None,
            target=None,
            mission=instance,
        )
        assert len(on_mission) == 1
        assert on_mission[0].perk == perk


class AnnounceDormantPerksTests(TestCase):
    """Direct unit tests on ``announce_dormant_perks``'s delivery contract."""

    def setUp(self) -> None:
        self.subject_character = CharacterFactory()
        self.subject_sheet = CharacterSheetFactory(character=self.subject_character)
        self.room = ObjectDBFactory(
            db_key="DormantAnnounceRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.subject_character.location = self.room
        self.subject_character.save()

    def _firing(self, *, name: str = "Last Bulwark", magnitude_tenths: int = 10) -> FiredPerk:
        perk = VowSituationalPerkFactory(name=name, announce_template="unused for dormant lines")
        return FiredPerk(
            perk=perk,
            holder=self.subject_sheet,
            magnitude_tenths=magnitude_tenths,
            rung_number=None,
        )

    def test_dormant_line_reaches_holder_not_another_room_occupant(self) -> None:
        """(a) NON-MOCKED delivery assertion (follows test_perk_announce.py's
        ``test_telnet_delivery_reaches_a_character_actually_in_the_room``
        pattern): mocks only the terminal ``.msg()`` calls -- never an
        intermediate broadcast primitive -- on the exact objects expected to
        receive (or not receive) the line. A bystander physically in the
        SAME room as the holder must receive NOTHING; the dormant line is
        HOLDER-only, never room-broadcast."""
        bystander = CharacterFactory(location=self.room)
        firing = self._firing(name="Last Bulwark")

        with (
            mock.patch.object(self.subject_character, "msg") as mock_subject_msg,
            mock.patch.object(bystander, "msg") as mock_bystander_msg,
        ):
            announce_dormant_perks([firing], subject=self.subject_sheet)

        mock_bystander_msg.assert_not_called()

        # Both dispatch channels (the WS interaction push + the telnet
        # companion) land on the SAME holder object -- find the positional
        # (telnet-companion) call among them and check its text.
        positional_calls = [c for c in mock_subject_msg.call_args_list if c.args]
        assert len(positional_calls) == 1
        (sent_text,) = positional_calls[0].args
        assert sent_text == "your vow lies dormant — Last Bulwark would have answered here"

    def test_empty_dormant_no_dispatch(self) -> None:
        with mock.patch.object(self.subject_character, "msg") as mock_msg:
            announce_dormant_perks([], subject=self.subject_sheet)

        mock_msg.assert_not_called()


class CheckBonusDormantWiringTests(TestCase):
    """``_situational_perk_check_bonus``'s dormant pass, exercised through
    the public ``perform_check`` seam (#2536 slice 3, Task 7)."""

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.check_type = CheckTypeFactory(name="Dormant Check")
        self.covenant = CovenantFactory()
        self.role = CovenantRoleFactory(covenant_type=self.covenant.covenant_type)

    def test_disengaged_role_announces_dormant_check_bonus_perk(self) -> None:
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            engaged=False,
        )
        perk = VowSituationalPerkFactory(
            covenant_role=self.role,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            beneficiary=PerkBeneficiary.SELF,
            check_type=None,
        )

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with mock.patch("world.covenants.perks.services.announce_dormant_perks") as mock_dormant:
            perform_check(self.character, self.check_type, situation_ctx=ctx)

        assert mock_dormant.call_count == 1
        (dormant_arg,), kwargs = mock_dormant.call_args
        assert len(dormant_arg) == 1
        assert dormant_arg[0].perk == perk
        assert kwargs["subject"] == self.sheet

    def test_engaged_role_never_announces_dormant(self) -> None:
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=self.covenant,
            covenant_role=self.role,
            engaged=True,
        )
        VowSituationalPerkFactory(
            covenant_role=self.role,
            effect_kind=PerkEffectKind.CHECK_BONUS,
            beneficiary=PerkBeneficiary.SELF,
            check_type=None,
        )

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)
        with mock.patch("world.covenants.perks.services.announce_dormant_perks") as mock_dormant:
            perform_check(self.character, self.check_type, situation_ctx=ctx)

        mock_dormant.assert_not_called()


class OutcomeGuaranteeDormantWiringTests(TestCase):
    """``_apply_outcome_guarantees``'s dormant pass (#2536 slice 3, Task 7,
    (d)): a dormant TIER_FLOOR/BOTCH_IMMUNITY perk announces ONLY when it
    would actually have bound against the RAW outcome."""

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.check_type = CheckTypeFactory(name="Dormant Guarantee Check")
        ResultChart.clear_cache()

    def _chart(self, *levels: int):
        chart = ResultChartFactory(rank_difference=0)
        outcomes = {}
        lo = 1
        for level in levels:
            outcome = CheckOutcomeFactory(name=f"L{level}", success_level=level)
            ResultChartOutcomeFactory(chart=chart, outcome=outcome, min_roll=lo, max_roll=lo + 9)
            outcomes[level] = outcome
            lo += 10
        return chart, outcomes

    def test_dormant_tier_floor_announces_only_when_it_would_have_bound(self) -> None:
        _chart, outcomes = self._chart(-2, -1, 1, 2)
        covenant = CovenantFactory()
        role = CovenantRoleFactory(covenant_type=covenant.covenant_type)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant=covenant, covenant_role=role, engaged=False
        )
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            effect_kind=PerkEffectKind.TIER_FLOOR,
            floor_success_level=1,
            beneficiary=PerkBeneficiary.SELF,
        )

        ctx = SituationContext(holder=self.sheet, subject=self.sheet, target=None, resolution=None)

        # Raw outcome (-1) is below the dormant floor (1) -- it WOULD have bound.
        with (
            mock.patch("world.covenants.perks.services.announce_dormant_perks") as mock_dormant,
            force_check_outcome(outcomes[-1]),
        ):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        self.assertEqual(result.outcome, outcomes[-1])
        assert mock_dormant.call_count == 1
        (dormant_arg,), kwargs = mock_dormant.call_args
        assert len(dormant_arg) == 1
        assert dormant_arg[0].perk == perk
        assert kwargs["subject"] == self.sheet

        # Raw outcome (2) is already at/above the dormant floor (1) -- silence.
        with (
            mock.patch("world.covenants.perks.services.announce_dormant_perks") as mock_dormant,
            force_check_outcome(outcomes[2]),
        ):
            result = perform_check(self.character, self.check_type, situation_ctx=ctx)

        self.assertEqual(result.outcome, outcomes[2])
        mock_dormant.assert_not_called()


class PowerTermDormantWiringTests(TestCase):
    """``vow_situational_power_term``'s dormant pass (#2536 slice 3, Task 7)
    -- the critical case: a subject with NO engaged role at ALL (their entire
    vow is dormant) still triggers the dormant announcement, even though the
    existing "no engaged role" guard short-circuits the LIVE power bonus to 0
    before the resolution query ever runs."""

    def setUp(self) -> None:
        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)

    def test_wholly_disengaged_subject_still_announces_dormant_power_bonus(self) -> None:
        covenant = CovenantFactory()
        role = CovenantRoleFactory(covenant_type=covenant.covenant_type)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant=covenant, covenant_role=role, engaged=False
        )
        perk = VowSituationalPerkFactory(
            covenant_role=role,
            effect_kind=PerkEffectKind.POWER_BONUS,
            beneficiary=PerkBeneficiary.SELF,
        )
        technique = TechniqueFactory()

        ctx = PowerTermContext(sheet=self.sheet, technique=technique, applicable_threads=[])
        with mock.patch("world.covenants.perks.services.announce_dormant_perks") as mock_dormant:
            result = vow_situational_power_term(ctx)

        # No engaged role anywhere -- the pre-existing cheap-exit guard still
        # returns 0 for the LIVE power bonus...
        assert result == 0
        # ...but the dormant pass ran anyway (ruling 2's loud OFF state).
        assert mock_dormant.call_count == 1
        (dormant_arg,), kwargs = mock_dormant.call_args
        assert len(dormant_arg) == 1
        assert dormant_arg[0].perk == perk
        assert kwargs["subject"] == self.sheet

    def test_engaged_role_elsewhere_never_announces_dormant_for_this_perk(self) -> None:
        """An ENGAGED role never produces a dormant firing for its own perk."""
        covenant = CovenantFactory()
        role = CovenantRoleFactory(covenant_type=covenant.covenant_type)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet, covenant=covenant, covenant_role=role, engaged=True
        )
        VowSituationalPerkFactory(
            covenant_role=role,
            effect_kind=PerkEffectKind.POWER_BONUS,
            beneficiary=PerkBeneficiary.SELF,
        )
        technique = TechniqueFactory()

        ctx = PowerTermContext(sheet=self.sheet, technique=technique, applicable_threads=[])
        with mock.patch("world.covenants.perks.services.announce_dormant_perks") as mock_dormant:
            vow_situational_power_term(ctx)

        mock_dormant.assert_not_called()
