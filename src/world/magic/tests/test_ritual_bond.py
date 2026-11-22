"""An Anima ritual with a partner (#5181): what it earns, what it does to the partner's fatigue,
the sentence the partner reads before agreeing, and the request that carries it."""

from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase

from actions.constants import ActionCategory
from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.types import CheckResult
from world.fatigue.services import get_or_create_fatigue_pool
from world.magic.constants import AnimaRitualEndorsement, GainSource, RitualExecutionKind
from world.magic.exceptions import RitualAlreadyPerformedThisScene
from world.magic.factories import (
    AnimaRitualPerformanceFactory,
    AnimaRitualResonanceAwardFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    SoulfrayConfigFactory,
    ensure_canonical_affinities,
)
from world.magic.models import AnimaRitualPerformance, ResonanceGrant
from world.magic.models.soulfray import AnimaRitualBudgetAward
from world.magic.services.anima import apply_anima_ritual_outcome
from world.magic.services.anima_ritual_action import (
    check_partner_ritual,
    ritual_consent_sentence,
)
from world.magic.services.ritual_bond import (
    apply_ritual_bond,
    partner_ritual_line,
    performer_ritual_line,
    ritual_partner_effect_sentence,
)
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.models import RosterTenure
from world.scenes.action_constants import ActionRequestStatus, ConsentDecision
from world.scenes.action_services import create_action_request, respond_to_action_request
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.traits.factories import CheckOutcomeFactory, ensure_level_ladder

_ACCRUE = "world.scenes.action_services.accrue"
_ROLL = "world.checks.services.perform_check_with_modifiers"


def _fatigue(sheet) -> int:
    return get_or_create_fatigue_pool(sheet).get_current(ActionCategory.SOCIAL)


class _Bond(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        _celestial, primal, abyssal = ensure_canonical_affinities()
        cls.abyssal, cls.primal = abyssal, primal
        cls.ruin = ResonanceFactory(name="Ruin", affinity=abyssal)
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)
        AnimaRitualResonanceAwardFactory(outcome_tier=cls.success, amount=6)

    def setUp(self) -> None:
        self.performer = CharacterSheetFactory()
        # A character nobody holds is a story NPC: the outward part is granted at once.
        self.partner = CharacterSheetFactory()
        self.ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION, service_function_path="", flow=None
        )
        self.performance = AnimaRitualPerformanceFactory(
            ritual=self.ritual, target_character=self.partner
        )
        # The ritual earns only for a resonance the performer holds.
        CharacterResonanceFactory(character_sheet=self.performer, resonance=self.ruin)

    def _set_fatigue_setting(self, affinity, value: int) -> None:
        affinity.ritual_partner_fatigue = value
        affinity.save()

    def _bond(self, *, resonance=None, outcome=None):
        return apply_ritual_bond(
            self.performer,
            self.partner,
            self.ritual,
            outcome or self.success,
            self.performance,
            primal=None,
            outward=resonance if resonance is not None else self.ruin,
        )


class ApplyRitualBondTests(_Bond):
    def test_pays_the_tiers_award_and_takes_the_partners_fatigue_for_a_positive_setting(
        self,
    ) -> None:
        self._set_fatigue_setting(self.abyssal, 10)

        bond = self._bond()

        self.assertEqual(bond.outward_granted, 6)
        self.assertEqual((bond.partner_fatigue_setting, bond.fatigue_change), (1, 10))
        self.assertEqual(_fatigue(self.partner), 10)
        grant = ResonanceGrant.objects.get(character_sheet=self.performer)
        self.assertEqual((grant.source, grant.amount), (GainSource.ANIMA_RITUAL, 6))

    def test_a_negative_setting_eases_the_partners_fatigue_and_never_below_zero(self) -> None:
        self._set_fatigue_setting(self.abyssal, -4)
        pool = get_or_create_fatigue_pool(self.partner)
        pool.set_current(ActionCategory.SOCIAL, 3)
        pool.save()

        bond = self._bond()

        self.assertEqual((bond.partner_fatigue_setting, bond.fatigue_change), (-1, -3))
        self.assertEqual(_fatigue(self.partner), 0)

    def test_a_zero_setting_leaves_the_partners_fatigue_alone(self) -> None:
        self._set_fatigue_setting(self.abyssal, 0)

        bond = self._bond()

        self.assertEqual((bond.partner_fatigue_setting, bond.fatigue_change), (0, 0))
        self.assertEqual(_fatigue(self.partner), 0)

    def test_the_affinity_of_the_rituals_resonance_decides_not_the_performers(self) -> None:
        self._set_fatigue_setting(self.abyssal, 10)
        self._set_fatigue_setting(self.primal, 0)
        wild = ResonanceFactory(name="Thorn", affinity=self.primal)
        CharacterResonanceFactory(character_sheet=self.performer, resonance=wild)
        CharacterAuraFactory(character=self.performer, celestial=0, primal=0, abyssal=100)

        bond = self._bond(resonance=wild)

        self.assertEqual(bond.fatigue_change, 0)

    def test_a_tier_with_no_award_earns_nothing_but_still_touches_the_partner(self) -> None:
        self._set_fatigue_setting(self.abyssal, 10)
        failure = CheckOutcomeFactory(name="Failure", success_level=-1)

        bond = self._bond(outcome=failure)

        self.assertEqual(bond.outward_granted, 0)
        self.assertFalse(ResonanceGrant.objects.filter(character_sheet=self.performer).exists())
        self.assertEqual(_fatigue(self.partner), 10)

    def test_a_ritual_naming_no_resonance_earns_nothing_and_does_nothing_to_the_partner(
        self,
    ) -> None:
        self._set_fatigue_setting(self.abyssal, 10)

        bond = apply_ritual_bond(
            self.performer,
            self.partner,
            self.ritual,
            self.success,
            self.performance,
            primal=None,
            outward=None,
        )

        self.assertIsNone(bond.outward_resonance)
        self.assertEqual(_fatigue(self.partner), 0)

    def test_the_kindled_share_adds_to_the_award_before_the_earn_rate(self) -> None:
        # Walkthrough: 6 + 50% of 6 = 9, and at the Abyssal earn rate of 150% that is 13.
        self.abyssal.earn_rate_percent = 150
        self.abyssal.save()
        CharacterAuraFactory(character=self.performer, celestial=0, primal=0, abyssal=100)
        fed = SimpleNamespace(fed_tier=SimpleNamespace(earn_percent=50))
        with (
            patch("world.magic.services.ritual_bond.kindled_for", return_value=fed),
            patch(
                "world.magic.services.ritual_bond.kindling_context_for",
                return_value=SimpleNamespace(resolution=None, mission=None),
            ),
        ):
            bond = self._bond()

        self.assertEqual(bond.outward_granted, 13)


class RitualLinesTests(_Bond):
    def test_the_consent_sentence_follows_the_sign_of_the_setting(self) -> None:
        for value, sentence in (
            (10, "It will add to your fatigue."),
            (-4, "It will ease your fatigue."),
            (0, ""),
        ):
            self._set_fatigue_setting(self.abyssal, value)
            self.assertEqual(ritual_partner_effect_sentence(self.ruin), sentence)
        self.assertEqual(ritual_partner_effect_sentence(None), "")

    def test_the_performers_and_partners_lines(self) -> None:
        self._set_fatigue_setting(self.abyssal, 10)
        bond = self._bond()

        self.assertEqual(
            performer_ritual_line(bond, "Tobin", 6),
            "Your ritual feeds on Tobin. You recover 6 anima. Your Ruin grows by 6.",
        )
        self.assertEqual(partner_ritual_line(bond, "Mara"), "Mara's ritual leaves you wearier.")

    def test_a_ritual_that_does_nothing_to_the_partner_reads_done_and_tells_them_nothing(
        self,
    ) -> None:
        self._set_fatigue_setting(self.abyssal, 0)
        bond = self._bond()

        self.assertEqual(
            performer_ritual_line(bond, "Tobin", 6),
            "Your ritual with Tobin is done. You recover 6 anima. Your Ruin grows by 6.",
        )
        self.assertEqual(partner_ritual_line(bond, "Mara"), "")


class AcceptingARitualRequestTests(TestCase):
    """The request a partner is asked, and what accepting it does (#5181)."""

    @classmethod
    def setUpTestData(cls) -> None:
        ensure_level_ladder()
        _celestial, _primal, cls.abyssal = ensure_canonical_affinities()
        cls.abyssal.ritual_partner_fatigue = 10
        cls.abyssal.save()
        cls.ruin = ResonanceFactory(name="Ruin", affinity=cls.abyssal)
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)
        AnimaRitualResonanceAwardFactory(outcome_tier=cls.success, amount=6)
        AnimaRitualBudgetAward.objects.create(outcome_tier=cls.success, budget=6)
        SoulfrayConfigFactory(ritual_severity_cost_per_point=1)

    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.scene = SceneFactory(is_active=True, location=RoomProfileFactory(objectdb=self.room))
        invalidate_active_scene_cache(self.room)
        self.mara = PersonaFactory()
        self.tobin = PersonaFactory()
        for persona in (self.mara, self.tobin):
            persona.character_sheet.character.location = self.room
        # A played character is asked; an NPC would answer at once.
        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.tobin.character_sheet),
            end_date=None,
        )
        self.sheet = self.mara.character_sheet
        self.ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=self.sheet.character.db_account,
        )
        RitualCheckConfigFactory(
            ritual=self.ritual, outward_resonance=self.ruin, check_type=CheckTypeFactory()
        )
        CharacterAnimaFactory(character=self.sheet, current=2, maximum=10)
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.ruin)

    def _request(self):
        return create_action_request(
            scene=self.scene,
            initiator_persona=self.mara,
            target_persona=self.tobin,
            action_key="anima_ritual",
            ritual_id=self.ritual.pk,
        )

    def _roll(self, request) -> CheckResult:
        return CheckResult(
            check_type=request.snapshot_check_type or self.ritual.check_config.check_type,
            outcome=self.success,
            chart=None,
            roller_rank=None,
            target_rank=None,
            rank_difference=0,
            trait_points=0,
            aspect_bonus=0,
            total_points=0,
        )

    def _accept(self, request) -> None:
        with patch(_ACCRUE), patch(_ROLL, return_value=self._roll(request)):
            respond_to_action_request(action_request=request, decision=ConsentDecision.ACCEPT)

    def test_the_pending_request_carries_the_sentence_before_the_partner_agrees(self) -> None:
        request = self._request()

        self.assertEqual(request.status, ActionRequestStatus.PENDING)
        self.assertEqual(ritual_consent_sentence(request), "It will add to your fatigue.")

    def test_accepting_rolls_the_rituals_own_check_and_applies_everything(self) -> None:
        request = self._request()

        self._accept(request)

        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        performance = AnimaRitualPerformance.objects.get(ritual=self.ritual)
        self.assertEqual(performance.target_character, self.tobin.character_sheet)
        self.assertEqual(self.sheet.character.anima.current, 8)
        self.assertEqual(_fatigue(self.tobin.character_sheet), 10)
        # Tobin is a player character, so the outward part waits for his answer.
        self.assertFalse(ResonanceGrant.objects.filter(character_sheet=self.sheet).exists())
        self.assertEqual(performance.endorsement, AnimaRitualEndorsement.PENDING)
        self.assertEqual(performance.outward_amount_pending, 6)
        self.assertEqual(performance.outward_resonance, self.ruin)

    def test_an_npc_partner_answers_at_once_and_is_treated_as_a_player_is(self) -> None:
        npc = PersonaFactory()
        npc.character_sheet.character.location = self.room
        with (
            patch(_ACCRUE),
            patch(_ROLL, return_value=self._roll(SimpleNamespace(snapshot_check_type=None))),
        ):
            request = create_action_request(
                scene=self.scene,
                initiator_persona=self.mara,
                target_persona=npc,
                action_key="anima_ritual",
                ritual_id=self.ritual.pk,
            )

        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        self.assertEqual(_fatigue(npc.character_sheet), 10)

    def test_a_ritual_cannot_be_asked_twice_in_a_scene(self) -> None:
        self._request()

        with self.assertRaises(ValidationError):
            check_partner_ritual(
                initiator_persona=self.mara, target_persona=self.tobin, scene=self.scene
            )

    def test_a_ritual_already_performed_in_the_scene_is_refused(self) -> None:
        AnimaRitualPerformance.objects.create(
            ritual=self.ritual, scene=self.scene, was_successful=True, outcome=self.success
        )

        with self.assertRaises(ValidationError):
            check_partner_ritual(
                initiator_persona=self.mara, target_persona=self.tobin, scene=self.scene
            )

    def test_you_cannot_be_your_own_partner(self) -> None:
        with self.assertRaises(ValidationError):
            check_partner_ritual(
                initiator_persona=self.mara, target_persona=self.mara, scene=self.scene
            )

    def test_a_partner_who_is_not_in_the_scene_and_place_is_refused(self) -> None:
        elsewhere = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        self.tobin.character_sheet.character.location = elsewhere

        with self.assertRaises(ValidationError):
            check_partner_ritual(
                initiator_persona=self.mara, target_persona=self.tobin, scene=self.scene
            )

    def test_a_partner_who_has_left_by_the_time_it_resolves_gets_no_effect(self) -> None:
        request = self._request()
        self.tobin.character_sheet.character.location = ObjectDBFactory(
            db_typeclass_path="typeclasses.rooms.Room"
        )

        self._accept(request)

        request.refresh_from_db()
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        self.assertFalse(AnimaRitualPerformance.objects.filter(ritual=self.ritual).exists())
        self.assertFalse(ResonanceGrant.objects.filter(character_sheet=self.sheet).exists())

    def test_one_account_cannot_perform_the_ritual_between_two_characters_it_plays(self) -> None:
        tobins = RosterTenure.objects.get(roster_entry__character_sheet=self.tobin.character_sheet)
        RosterTenureFactory(
            roster_entry=RosterEntryFactory(character_sheet=self.sheet),
            player_data=tobins.player_data,
            end_date=None,
        )

        with self.assertRaisesMessage(
            ValidationError, "You cannot perform your ritual with another character you play."
        ):
            check_partner_ritual(
                initiator_persona=self.mara, target_persona=self.tobin, scene=self.scene
            )

    def test_the_second_of_two_racing_performances_pays_nothing(self) -> None:
        # Both passed the once-per-scene check before either committed; the first now has.
        AnimaRitualPerformance.objects.create(
            ritual=self.ritual, scene=self.scene, was_successful=True, outcome=self.success
        )

        with self.assertRaises(RitualAlreadyPerformedThisScene):
            apply_anima_ritual_outcome(
                ritual=self.ritual,
                outcome=self.success,
                scene=self.scene,
                character_sheet=self.sheet,
            )
        self.assertEqual(self.sheet.character.anima.current, 2)
