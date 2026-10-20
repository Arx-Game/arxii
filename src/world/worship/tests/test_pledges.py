"""Pledges and sacrifices (#4333 slice 2): walkthrough A steps 1 and 2, closing and lapse.

Numbers follow the issue's walkthrough A: a Chosen of the being earns at 200%; a
favor target of 20 within two game weeks; favored deeds at 100% of the grant,
associated at 50%; a sacrifice is a check eased by what the item means to its giver
(never its price) whose outcome pays 6 / 4 / 2 / 0 / 0 base favor, x2 points for a
favored facet; a weekly deed cap of 8 base favor; closing awards of 8 / 5 / 3 / 2 / 0 by
outcome. Check rolls are forced through ``force_check_outcome``; everything else is the
real path.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import ObjectDBFactory, RoomProfileFactory
from world.action_points.factories import ActionPointPoolFactory
from world.ceremonies.models import CeremonyOffering
from world.ceremonies.services import sacrifice_items
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.distinctions.factories import CharacterDistinctionFactory, DistinctionFactory
from world.items.constants import MeaningSignalKind
from world.items.factories import (
    EquippedItemFactory,
    ItemFacetFactory,
    ItemInstanceFactory,
    QualityTierFactory,
)
from world.items.models import ItemInstance
from world.magic.constants import GainSource, TargetKind
from world.magic.factories import CharacterResonanceFactory, FacetFactory
from world.magic.models import Thread
from world.magic.services.gain import (
    outfit_trickle_tick,
    residence_trickle_tick,
    set_residence,
    tag_room_resonance,
)
from world.magic.services.resonance import grant_resonance
from world.projects.constants import ProjectKind, ProjectStatus
from world.projects.services import scan_active_projects
from world.roster.factories import grant_test_tenure
from world.scenes.action_constants import MIN_DIFFICULTY_POINTS
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Interaction
from world.traits.factories import CheckOutcomeFactory
from world.worship.constants import (
    BeingResonanceTier,
    FavorAwardKind,
    PledgeCreditSource,
    PledgeState,
    RiteTier,
)
from world.worship.exceptions import (
    PledgeAlreadyOpen,
    PledgeNotReady,
    PledgeSpanEnded,
    PledgeUnavailable,
    SacrificeRefused,
)
from world.worship.factories import (
    BeingFacetFactory,
    BeingResonanceFactory,
    DevotionStandingFactory,
    FavorOutcomeAwardFactory,
    PledgeFactory,
    RiteKindFactory,
    ShrineDetailsFactory,
    WorshippedBeingFactory,
    WorshipRiteFactory,
    WorshipRiteTierAwardFactory,
)
from world.worship.invocation_services import get_devotion_config, invocation_difficulty
from world.worship.models import (
    DevotionStanding,
    PatronageValence,
    Pledge,
    PledgeCredit,
    PledgeDetails,
    Prayer,
    WorshipRitePerformance,
)
from world.worship.pledge_services import (
    close_pledge,
    open_pledge_for,
    pledge_card,
    take_pledge,
)
from world.worship.rite_services import perform_worship_rite
from world.worship.services import bump_devotion

_OUTCOMES = (
    ("Critical Success", 2),
    ("Success", 1),
    ("Partial Success", 0),
    ("Failure", -1),
    ("Critical Failure", -2),
)
_CLOSING = {"Critical Success": 8, "Success": 5, "Partial Success": 3, "Failure": 2}
_SACRIFICE = {"Critical Success": 6, "Success": 4, "Partial Success": 2}


class PledgeTestBase(TestCase):
    """Ysmay, Ombrin's Chosen (earning rate 200%), at Ombrin's shrine in a live scene."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.outcomes = {
            name: CheckOutcomeFactory(name=name, success_level=level) for name, level in _OUTCOMES
        }
        config = get_devotion_config()
        for name, amount in _CLOSING.items():
            FavorOutcomeAwardFactory(
                config=config,
                kind=FavorAwardKind.CLOSING,
                outcome_tier=cls.outcomes[name],
                amount=amount,
            )
        for name, amount in _SACRIFICE.items():
            FavorOutcomeAwardFactory(
                config=config,
                kind=FavorAwardKind.SACRIFICE,
                outcome_tier=cls.outcomes[name],
                amount=amount,
            )
        config.invocation_check_type = CheckTypeFactory()
        config.save(update_fields=["invocation_check_type"])
        for outcome in cls.outcomes.values():
            WorshipRiteTierAwardFactory(
                tier=RiteTier.DEVOTIONAL, outcome_tier=outcome, resonance_amount=4, favor_amount=2
            )

        cls.sheet = CharacterSheetFactory()
        cls.tenure = grant_test_tenure(cls.sheet)
        cls.account = cls.tenure.player_data.account
        cls.room = ObjectDBFactory(db_key="Shrine Room", db_typeclass_path="typeclasses.rooms.Room")
        cls.profile = RoomProfileFactory(objectdb=cls.room)
        cls.sheet.character.db_location = cls.room
        cls.sheet.character.save(update_fields=["db_location"])
        cls.scene = SceneFactory(location=cls.profile, is_active=True)
        SceneParticipationFactory(scene=cls.scene, account=cls.account)
        ActionPointPoolFactory(character=cls.sheet, current=20, maximum=20)

        cls.being = WorshippedBeingFactory(name="Ombrin", resonance_pool=100)
        cls.favored = BeingResonanceFactory(being=cls.being, tier=BeingResonanceTier.FAVORED)
        cls.associated = BeingResonanceFactory(being=cls.being, tier=BeingResonanceTier.ASSOCIATED)
        cls.silk = BeingFacetFactory(being=cls.being, facet__name="Silk").facet
        cls.rite = WorshipRiteFactory(
            being=cls.being,
            kind=RiteKindFactory(name="Vigil", tier=RiteTier.DEVOTIONAL),
            name="Ombrin's rite",
            resonance=cls.associated,
        )
        ShrineDetailsFactory(feature_instance__room_profile=cls.profile, being=cls.being)
        DevotionStandingFactory(
            character_sheet=cls.sheet,
            being=cls.being,
            valence=PatronageValence.DEVOTIONAL,
            established_at=timezone.now(),
        )
        cls.pledge = PledgeFactory(
            being=cls.being, favor_target=20, span_weeks=2, closing_rite=cls.rite
        )

    def _favor(self) -> int:
        return DevotionStanding.objects.get(character_sheet=self.sheet, being=self.being).favor

    def _carried_item(
        self, value: int = 20, facet=None, *, meaningful: bool = True, days: int = 30
    ) -> ItemInstance:
        """An item the sheet carries. ``meaningful``: the sheet made it and has held it
        ``days`` days, so own work 1 plus carried 1 is 2 meaning points. Otherwise it is
        bought off a stall with no history at all, worth nothing whatever its ``value``."""
        obj = ObjectDBFactory(db_key="offering", db_typeclass_path="typeclasses.objects.Object")
        obj.db_location = self.sheet.character
        obj.save(update_fields=["db_location"])
        item = ItemInstanceFactory(template__value=value, game_object=obj)
        item.holder_character_sheet = self.sheet
        item.held_since = timezone.now() - timedelta(days=days)
        if meaningful:
            item.crafter_character_sheet = self.sheet
        item.save(update_fields=["holder_character_sheet", "held_since", "crafter_character_sheet"])
        if facet is not None:
            ItemFacetFactory(item_instance=item, facet=facet)
        return item

    def _grant(self, being_resonance, amount: int, source: GainSource = GainSource.COMPROMISE):
        """A deed by default: a compromising act is an action, so it is a deed.

        STAFF_GRANT is passive (see ``PASSIVE_DEED_SOURCES``) and is tested on its own.
        """
        return grant_resonance(self.sheet, being_resonance.resonance, amount, source=source)

    def _reach_target(self, details: PledgeDetails, progress: int = 20) -> None:
        details.project.current_progress = progress
        details.project.save(update_fields=["current_progress"])


class TakePledgeTests(PledgeTestBase):
    def test_taking_a_pledge_opens_a_pledge_project_with_a_prayer(self) -> None:
        details = take_pledge(self.sheet, self.pledge, prayer_text="[player-written prayer]")

        project = details.project
        self.assertEqual(project.kind, ProjectKind.PLEDGE)
        self.assertEqual(project.status, ProjectStatus.ACTIVE)
        self.assertEqual(project.threshold_target, 20)
        # Pledging at the shrine with a prayer is the week's holy-site prayer: 1 base
        # at 200% counts toward the pledge it was made with.
        self.assertEqual(project.current_progress, 2)
        self.assertAlmostEqual(
            project.time_limit - project.started_at, timedelta(days=14), delta=timedelta(seconds=1)
        )
        self.assertEqual(details.prayer, Prayer.objects.get(character_sheet=self.sheet))
        self.assertEqual(details.prayer.text, "[player-written prayer]")

    def test_one_open_pledge_per_character(self) -> None:
        take_pledge(self.sheet, self.pledge)
        other = PledgeFactory(being=self.being)

        with self.assertRaises(PledgeAlreadyOpen):
            take_pledge(self.sheet, other)
        self.assertEqual(PledgeDetails.objects.filter(character_sheet=self.sheet).count(), 1)

    def test_an_inactive_pledge_is_refused(self) -> None:
        self.pledge.is_active = False
        self.pledge.save(update_fields=["is_active"])

        with self.assertRaises(PledgeUnavailable):
            take_pledge(self.sheet, self.pledge)

    def test_closing_rite_tier_1_or_2_only(self) -> None:
        ceremony_rite = WorshipRiteFactory(
            being=self.being, kind=RiteKindFactory(name="Great rite", tier=RiteTier.PERILOUS)
        )
        pledge = Pledge(being=self.being, name="Too much", closing_rite=ceremony_rite)
        with self.assertRaises(ValidationError) as caught:
            pledge.full_clean()
        self.assertIn("closing_rite", caught.exception.message_dict)

        foreign = WorshipRiteFactory()
        pledge.closing_rite = foreign
        with self.assertRaises(ValidationError):
            pledge.full_clean()


class ProgressTests(PledgeTestBase):
    def test_walkthrough_a_progress_reaches_twenty(self) -> None:
        """A mission-like grant of 3 favored (+6), an endorsement-like grant of 2
        associated (+2), a sacrifice of 2 points with Silk (+8) and the rite (+4)."""
        details = take_pledge(self.sheet, self.pledge)

        self._grant(self.favored, 3)
        self._grant(self.associated, 2)
        with force_check_outcome(self.outcomes["Success"]):
            sacrifice_items(self.sheet, [self._carried_item(facet=self.silk)])
        with force_check_outcome(self.outcomes["Success"]):
            perform_worship_rite(self.sheet, self.rite, scene=self.scene)

        self.assertEqual(open_pledge_for(self.sheet).project.current_progress, 20)
        rows = list(PledgeCredit.objects.filter(pledge_details=details))
        self.assertEqual(
            [(c.source, c.base, c.earning_rate_percent, c.credited) for c in rows],
            [
                (PledgeCreditSource.DEED, 3, 200, 6),
                (PledgeCreditSource.DEED, 1, 200, 2),
                (PledgeCreditSource.SACRIFICE, 4, 200, 8),
                (PledgeCreditSource.RITE, 2, 200, 4),
            ],
        )
        card = pledge_card(open_pledge_for(self.sheet))
        self.assertEqual(card.state, PledgeState.READY)
        self.assertEqual(card.progress, 20)
        self.assertEqual(
            card.credits[2].calculation,
            "carried 1 (held 30 days), own work 1 (made by the holder) = 2, "
            "x2 Silk = 4 points, eased 40."
            " Success: 4 base, at 200% = +8",
        )
        self.assertEqual(self._favor(), 20)

    def test_bump_devotion_updates_open_pledge_progress(self) -> None:
        details = take_pledge(self.sheet, self.pledge)

        bump = bump_devotion(self.sheet, self.being, 3)

        self.assertEqual(bump.credited, 6)
        self.assertEqual(open_pledge_for(self.sheet).project.current_progress, 6)
        self.assertEqual(bump.pledge_credit.pledge_details, details)

    def test_favor_for_another_being_does_not_count(self) -> None:
        take_pledge(self.sheet, self.pledge)

        bump_devotion(self.sheet, WorshippedBeingFactory(), 5)

        self.assertEqual(open_pledge_for(self.sheet).project.current_progress, 0)
        self.assertFalse(PledgeCredit.objects.exists())

    def test_no_open_pledge_records_nothing(self) -> None:
        bump = bump_devotion(self.sheet, self.being, 3)

        self.assertEqual(bump.credited, 6)
        self.assertIsNone(bump.pledge_credit)
        self.assertFalse(PledgeCredit.objects.exists())


class DeedTests(PledgeTestBase):
    def test_credit_pledge_deed_tiers_and_cap(self) -> None:
        take_pledge(self.sheet, self.pledge)

        self._grant(self.favored, 3)  # 3 base
        self._grant(self.associated, 3)  # 50% of 3 rounds down to 1
        self._grant(BeingResonanceFactory(being=WorshippedBeingFactory()), 5)  # not valued
        self._grant(self.favored, 10)  # 4 base left under the cap of 8

        deeds = PledgeCredit.objects.filter(source=PledgeCreditSource.DEED).order_by("pk")
        self.assertEqual([d.base for d in deeds], [3, 1, 4])
        self.assertEqual(sum(d.credited for d in deeds), 16)
        self._grant(self.favored, 5)  # the cap is spent
        self.assertEqual(PledgeCredit.objects.filter(source=PledgeCreditSource.DEED).count(), 3)

    def test_a_small_associated_grant_earns_at_least_one(self) -> None:
        take_pledge(self.sheet, self.pledge)

        self._grant(self.associated, 1)

        self.assertEqual(PledgeCredit.objects.get().base, 1)

    def test_deeds_need_an_open_pledge(self) -> None:
        self._grant(self.favored, 3)

        self.assertFalse(
            DevotionStanding.objects.filter(
                character_sheet=self.sheet, being=self.being, favor__gt=0
            ).exists()
        )

    def test_a_worship_rite_grant_is_not_a_deed(self) -> None:
        take_pledge(self.sheet, self.pledge)
        with force_check_outcome(self.outcomes["Success"]):
            perform_worship_rite(self.sheet, self.rite, scene=self.scene)

        self.assertEqual(
            list(PledgeCredit.objects.values_list("source", flat=True)), [PledgeCreditSource.RITE]
        )

    # Favor comes only from a character's actions (owner ruling 2026-10-16). Each passive
    # grant source below still grants resonance, but earns no pledge favor.

    def test_a_residence_trickle_during_an_open_pledge_credits_no_favor(self) -> None:
        take_pledge(self.sheet, self.pledge)
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.favored.resonance)
        tag_room_resonance(self.profile, self.favored.resonance)
        set_residence(self.sheet, self.profile)
        credits_before = PledgeCredit.objects.count()
        favor_before = self._favor()

        summary = residence_trickle_tick()

        self.assertEqual(summary.residence_grants_issued, 1)
        self.assertEqual(PledgeCredit.objects.count(), credits_before)
        self.assertEqual(self._favor(), favor_before)

    def test_an_outfit_trickle_during_an_open_pledge_credits_no_favor(self) -> None:
        take_pledge(self.sheet, self.pledge)
        facet = FacetFactory()
        item = ItemInstanceFactory(quality_tier=QualityTierFactory(stat_multiplier=2))
        ItemFacetFactory(
            item_instance=item,
            facet=facet,
            attachment_quality_tier=QualityTierFactory(stat_multiplier=3),
        )
        EquippedItemFactory(character=self.sheet, item_instance=item)
        self.sheet.character.equipped_items.invalidate()
        Thread.objects.create(
            owner=self.sheet,
            resonance=self.favored.resonance,
            target_kind=TargetKind.FACET,
            target_facet=facet,
            level=2,
            developed_points=0,
        )
        credits_before = PledgeCredit.objects.count()
        favor_before = self._favor()

        grants_issued = outfit_trickle_tick()

        self.assertEqual(grants_issued, 1)
        self.assertEqual(PledgeCredit.objects.count(), credits_before)
        self.assertEqual(self._favor(), favor_before)

    def test_a_distinction_grant_during_an_open_pledge_credits_no_favor(self) -> None:
        take_pledge(self.sheet, self.pledge)
        distinction = CharacterDistinctionFactory(
            character=self.sheet, distinction=DistinctionFactory()
        )
        credits_before = PledgeCredit.objects.count()
        favor_before = self._favor()

        grant_resonance(
            self.sheet,
            self.favored.resonance,
            3,
            source=GainSource.DISTINCTION,
            source_character_distinction=distinction,
        )

        self.assertEqual(PledgeCredit.objects.count(), credits_before)
        self.assertEqual(self._favor(), favor_before)

    def test_a_staff_grant_during_an_open_pledge_credits_no_favor(self) -> None:
        take_pledge(self.sheet, self.pledge)
        credits_before = PledgeCredit.objects.count()
        favor_before = self._favor()

        self._grant(self.favored, 3, source=GainSource.STAFF_GRANT)

        self.assertEqual(PledgeCredit.objects.count(), credits_before)
        self.assertEqual(self._favor(), favor_before)


class SacrificeTests(PledgeTestBase):
    def _sacrifice(self, outcome_name: str, *items, **kwargs):
        with force_check_outcome(self.outcomes[outcome_name]) as capture:
            result = sacrifice_items(self.sheet, list(items), **kwargs)
        return result, capture

    def test_shrine_sacrifice_offering_row(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        item = self._carried_item(20, facet=self.silk)
        pool_before = self.being.resonance_pool

        outcome, _ = self._sacrifice("Success", item)

        offering = CeremonyOffering.objects.get()
        self.assertIsNone(offering.ceremony)
        self.assertEqual(offering.being, self.being)
        self.assertEqual(offering.pledge_details, details)
        self.assertEqual(offering.facet, self.silk)
        self.assertEqual(offering.item_value, 20)
        self.assertEqual(offering.outcome_tier, self.outcomes["Success"])
        self.assertTrue(offering.counted)
        self.assertEqual(
            [(s.kind, s.points) for s in offering.signals.all()],
            [(MeaningSignalKind.CARRIED, 1), (MeaningSignalKind.OWN_WORK, 1)],
        )
        # Soft-destroyed: out of play, design kept (#4461).
        self.assertIsNotNone(ItemInstance.objects.get(pk=item.pk).destroyed_at)
        self.being.refresh_from_db()
        # 2 points doubled for Silk = 4, at the config's 5 pool per point.
        self.assertEqual(self.being.resonance_pool, pool_before + 20)
        self.assertEqual(outcome.site, "shrine")
        self.assertEqual(outcome.items[0].credited, 8)
        line = Interaction.objects.get(mode=InteractionMode.OUTCOME)
        self.assertIn("sacrifices", line.content)
        self.assertIn("at Ombrin's shrine", line.content)

    def test_the_gm_sees_the_signals_and_the_roll_of_a_sacrifice(self) -> None:
        from world.worship.answer_services import sacrifice_detail

        self._sacrifice("Success", self._carried_item(facet=self.silk))

        detail = sacrifice_detail(CeremonyOffering.objects.get())

        self.assertEqual(
            [(s.kind_name, s.points) for s in detail.signals], [("Carried", 1), ("Own work", 1)]
        )
        self.assertEqual(
            (detail.points, detail.facet_name, detail.counted, detail.outcome_name),
            (2, "Silk", True, "Success"),
        )

    def test_a_bought_item_earns_nothing_whatever_it_cost(self) -> None:
        item = self._carried_item(400, meaningful=False, days=200)
        pool_before = self.being.resonance_pool

        with force_check_outcome(self.outcomes["Critical Success"]) as capture:
            outcome = sacrifice_items(self.sheet, [item])

        self.assertIsNone(capture.check_type)  # no roll
        self.assertEqual(outcome.items[0].credited, 0)
        self.assertEqual(self._favor(), 0)
        self.being.refresh_from_db()
        self.assertEqual(self.being.resonance_pool, pool_before)
        offering = CeremonyOffering.objects.get()
        self.assertFalse(offering.counted)
        self.assertIsNone(offering.outcome_tier)
        self.assertEqual(offering.signals.count(), 0)
        self.assertIsNotNone(ItemInstance.objects.get(pk=item.pk).destroyed_at)

    def test_meaning_eases_the_check_and_the_price_never_does(self) -> None:
        """Daunting 75 with the Chosen ease (favor 0), 2 points x 10 eased off."""
        cheap = self._carried_item(1)
        dear = self._carried_item(9000)

        _, first = self._sacrifice("Success", cheap)
        _, second = self._sacrifice("Success", dear)

        self.assertEqual(first.target_difficulty, second.target_difficulty)
        base = invocation_difficulty(self.sheet, self.being).points
        self.assertEqual(first.target_difficulty, max(base - 20, MIN_DIFFICULTY_POINTS))

    def test_the_outcome_picks_the_base_favor(self) -> None:
        results = {
            name: self._sacrifice(name, self._carried_item())[0].items[0].credited
            for name in ("Partial Success", "Success")
        }

        # The Chosen earns at 200%: 2 and 4 base.
        self.assertEqual(results, {"Partial Success": 4, "Success": 8})

    def test_a_failed_roll_pays_nothing_but_the_pool_still_grows(self) -> None:
        pool_before = self.being.resonance_pool

        outcome, _ = self._sacrifice("Failure", self._carried_item())

        self.assertEqual(outcome.items[0].credited, 0)
        self.being.refresh_from_db()
        self.assertEqual(self.being.resonance_pool, pool_before + 10)

    def test_the_weekly_limit_counts_items_with_points_only(self) -> None:
        limit = get_devotion_config().sacrifices_per_week
        bought = self._carried_item(500, meaningful=False)
        items = [self._carried_item() for _ in range(limit + 1)]

        # force_check_outcome is single-shot, so every roll in this batch is stubbed.
        with patch(
            "world.worship.sacrifice_services.roll_sacrifice",
            return_value=SimpleNamespace(outcome=self.outcomes["Success"]),
        ):
            outcome = sacrifice_items(self.sheet, [bought, *items])

        credited = [item.credited for item in outcome.items]
        self.assertEqual(credited, [0] + [8] * limit + [0])
        self.assertEqual(CeremonyOffering.objects.filter(counted=True).count(), limit)

    def test_a_critical_failure_closes_the_beings_hand_for_the_week(self) -> None:
        self._sacrifice("Critical Failure", self._carried_item())

        outcome, capture = self._sacrifice("Critical Success", self._carried_item())

        self.assertIsNone(capture.check_type)
        self.assertEqual(outcome.items[0].credited, 0)

    def test_sacrifice_refuses_before_giving_anything_up_without_a_check_type(self) -> None:
        config = get_devotion_config()
        config.invocation_check_type = None
        config.save(update_fields=["invocation_check_type"])
        item = self._carried_item()

        with self.assertRaises(SacrificeRefused):
            sacrifice_items(self.sheet, [item])
        self.assertIsNone(ItemInstance.objects.get(pk=item.pk).destroyed_at)

    def test_sacrifice_needs_a_holy_site(self) -> None:
        elsewhere = ObjectDBFactory(db_key="Road", db_typeclass_path="typeclasses.rooms.Room")
        RoomProfileFactory(objectdb=elsewhere)
        item = self._carried_item(20)
        self.sheet.character.db_location = elsewhere
        self.sheet.character.save(update_fields=["db_location"])

        with self.assertRaises(SacrificeRefused):
            sacrifice_items(self.sheet, [item])
        self.assertTrue(ItemInstance.objects.filter(pk=item.pk).exists())

    def test_an_item_not_carried_is_refused(self) -> None:
        loose = ItemInstanceFactory(template__value=20)

        with self.assertRaises(SacrificeRefused):
            sacrifice_items(self.sheet, [loose])


class CloseTests(PledgeTestBase):
    def _close(self, outcome_name: str):
        with force_check_outcome(self.outcomes[outcome_name]):
            return close_pledge(self.sheet, scene=self.scene)

    def test_close_pays_closing_award_only(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        self._reach_target(details)
        favor_before = self._favor()

        outcome = self._close("Success")

        self.assertTrue(outcome.resolved)
        self.assertEqual((outcome.award_base, outcome.award), (5, 10))
        self.assertEqual(self._favor(), favor_before + 10)
        details = PledgeDetails.objects.get(pk=details.pk)
        self.assertEqual(details.project.status, ProjectStatus.COMPLETED)
        performance = WorshipRitePerformance.objects.get(character_sheet=self.sheet)
        self.assertEqual(details.closing_performance, performance)
        self.assertEqual((performance.favor_granted, performance.resonance_granted), (0, 0))
        closing = PledgeCredit.objects.get(source=PledgeCreditSource.CLOSING)
        self.assertEqual(closing.credited, 10)
        self.assertEqual(details.project.current_progress, 20)  # the award adds no progress
        self.assertEqual(pledge_card(details).state, PledgeState.CLOSED)

    def test_close_retry_after_failure(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        self._reach_target(details)
        favor_before = self._favor()

        first = self._close("Failure")

        self.assertFalse(first.resolved)
        details = PledgeDetails.objects.get(pk=details.pk)
        self.assertEqual(details.close_attempts, 1)
        self.assertEqual(details.project.status, ProjectStatus.ACTIVE)
        self.assertEqual(self._favor(), favor_before)
        self.assertTrue(pledge_card(details).retry_available)

        second = self._close("Critical Failure")

        self.assertTrue(second.resolved)
        details = PledgeDetails.objects.get(pk=details.pk)
        self.assertEqual(details.close_attempts, 2)
        self.assertEqual(details.project.status, ProjectStatus.FAILED)
        self.assertEqual(second.award, 0)  # Critical Failure's closing award is 0

    def test_a_failed_retry_pays_the_failure_award(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        self._reach_target(details)
        self._close("Failure")

        second = self._close("Failure")

        self.assertTrue(second.resolved)
        self.assertEqual((second.award_base, second.award), (2, 4))

    def test_close_refused_below_target_and_after_the_span(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        self._reach_target(details, 19)
        with self.assertRaises(PledgeNotReady):
            self._close("Success")

        self._reach_target(details)
        details.project.time_limit = timezone.now() - timedelta(minutes=1)
        details.project.save(update_fields=["time_limit"])
        with self.assertRaises(PledgeSpanEnded):
            self._close("Success")
        self.assertFalse(WorshipRitePerformance.objects.exists())

    def test_close_sets_resolving_atomically(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        self._reach_target(details)

        with (
            patch(
                "world.worship.pledge_services.closing_award_amount",
                side_effect=RuntimeError("boom"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self._close("Success")

        details = PledgeDetails.objects.get(pk=details.pk)
        self.assertEqual(details.project.status, ProjectStatus.ACTIVE)
        self.assertIsNone(details.closing_performance)
        self.assertEqual(details.close_attempts, 0)
        self.assertEqual(open_pledge_for(self.sheet).pk, details.pk)


class LapseTests(PledgeTestBase):
    def _expire(self, details: PledgeDetails, progress: int) -> None:
        details.project.current_progress = progress
        details.project.time_limit = timezone.now() - timedelta(minutes=1)
        details.project.save(update_fields=["current_progress", "time_limit"])

    def test_pledge_at_target_stays_active(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        self._reach_target(details, 25)

        scan_active_projects()

        self.assertEqual(
            PledgeDetails.objects.get(pk=details.pk).project.status, ProjectStatus.ACTIVE
        )

    def test_lapse_half_target_pays_partial_award(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        self._expire(details, 10)
        favor_before = self._favor()

        scan_active_projects()

        details = PledgeDetails.objects.get(pk=details.pk)
        self.assertEqual(details.project.status, ProjectStatus.FAILED)
        lapse = PledgeCredit.objects.get(source=PledgeCreditSource.LAPSE)
        self.assertEqual((lapse.base, lapse.credited), (3, 6))
        self.assertEqual(self._favor(), favor_before + 6)
        self.assertEqual(details.project.current_progress, 10)
        self.assertEqual(pledge_card(details).state, PledgeState.LAPSED)

    def test_lapse_below_half_pays_nothing(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        bump_devotion(self.sheet, self.being, 4)  # 8 credited: below half of 20
        self._expire(details, 8)
        favor_before = self._favor()

        scan_active_projects()

        details = PledgeDetails.objects.get(pk=details.pk)
        self.assertEqual(details.project.status, ProjectStatus.FAILED)
        self.assertFalse(
            PledgeCredit.objects.filter(
                source__in=[PledgeCreditSource.LAPSE, PledgeCreditSource.CLOSING]
            ).exists()
        )
        self.assertEqual(self._favor(), favor_before)  # earned favor is kept

    def test_a_lapse_at_the_target_pays_the_partial_award_too(self) -> None:
        details = take_pledge(self.sheet, self.pledge)
        self._expire(details, 20)

        scan_active_projects()

        details = PledgeDetails.objects.get(pk=details.pk)
        self.assertEqual(details.project.status, ProjectStatus.COMPLETED)
        self.assertEqual(PledgeCredit.objects.get(source=PledgeCreditSource.LAPSE).base, 3)
        self.assertEqual(pledge_card(details).state, PledgeState.LAPSED)


class PledgeApiTests(PledgeTestBase):
    """The web reads: pledge types, what earns favor, the holy site here, the card."""

    def _client(self, account=None):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=account or self.account)
        return client

    def test_pledge_types_and_service_terms(self) -> None:
        client = self._client()
        entry = self.tenure.roster_entry_id

        pledges = client.get(f"/api/worship/pledges/?being={self.being.pk}").json()["results"]
        terms = client.get(
            f"/api/worship/beings/{self.being.pk}/service-terms/?entry_id={entry}"
        ).json()
        sites = client.get(f"/api/worship/beings/holy-site/?entry_id={entry}").json()

        self.assertEqual([row["id"] for row in pledges], [self.pledge.pk])
        self.assertEqual(pledges[0]["closing_rite_name"], "Ombrin's rite")
        self.assertEqual(
            terms["rate"], {"base": 100, "chosen_bonus": 100, "modifiers": 0, "total": 200}
        )
        self.assertEqual(terms["weekly_deed_cap"], 8)
        self.assertEqual(terms["lines"][0]["amount"], "100% of amount")
        self.assertIn("Silk facet count x2", terms["lines"][2]["label"])
        self.assertEqual(
            sites, [{"being_id": self.being.pk, "being_name": "Ombrin", "site": "shrine"}]
        )

    def test_the_owner_reads_their_pledge_card_and_a_stranger_does_not(self) -> None:
        from evennia.accounts.models import AccountDB

        details = take_pledge(self.sheet, self.pledge)
        bump_devotion(self.sheet, self.being, 3)

        cards = (
            self._client()
            .get(f"/api/worship/pledge-cards/?character_sheet={self.sheet.pk}")
            .json()["results"]
        )
        stranger = AccountDB.objects.create(username="stranger-4362", is_staff=False)
        hidden = self._client(stranger).get("/api/worship/pledge-cards/").json()["results"]

        self.assertEqual([card["id"] for card in cards], [details.pk])
        card = cards[0]
        self.assertEqual((card["state"], card["progress"], card["target"]), ("open", 6, 20))
        self.assertEqual(card["credits"][0]["calculation"], "3 base, at 200% = +6")
        self.assertEqual(card["pledge"]["name"], self.pledge.name)
        self.assertEqual(hidden, [])

    def test_service_terms_for_a_named_sheet_only_when_you_play_it(self) -> None:
        from evennia.accounts.models import AccountDB

        url = f"/api/worship/beings/{self.being.pk}/service-terms/?character_sheet={self.sheet.pk}"
        own = self._client().get(url)
        stranger = AccountDB.objects.create(username="stranger-terms-4362", is_staff=False)
        other = self._client(stranger).get(url)

        self.assertEqual(own.json()["rate"]["total"], 200)
        self.assertEqual(other.status_code, 403)


class WebDispatchTests(PledgeTestBase):
    """The web dispatches pks, not names: the pledge, the being and the items."""

    def test_pray_take_and_sacrifice_by_pk(self) -> None:
        from actions.definitions.worship import PrayAction, SacrificeAction, TakePledgeAction

        character = self.sheet.character
        prayed = PrayAction().run(actor=character, being=self.being.pk, text="[prayer]")
        taken = TakePledgeAction().run(actor=character, pledge=self.pledge.pk, prayer="")
        item = self._carried_item(20, facet=self.silk)
        with force_check_outcome(self.outcomes["Success"]):
            given = SacrificeAction().run(actor=character, item_ids=[item.pk], being=self.being.pk)

        self.assertTrue(prayed.success, prayed.message)
        self.assertTrue(taken.success, taken.message)
        self.assertIn("Your earning rate with Ombrin: 200% (100% + 100% Chosen).", taken.message)
        self.assertTrue(given.success, given.message)
        self.assertIn(
            "carried 1 (held 30 days), own work 1 (made by the holder) = 2, "
            "x2 Silk = 4 points, eased 40."
            " Success: 4 base, at 200% = +8 favor.",
            given.message,
        )
