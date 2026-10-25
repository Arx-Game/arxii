"""Journeys: threads are capped by character level and their thresholds fire at the
level a player sees (#4585).

A thread level is stored x10, like a stat: stored 30 shows 3. Every authored thread
threshold (the crossings at 3, 6, 11, 16 and 21, a covenant sub-role's unlock level, a
signature flourish's minimum) is a shown level, so it is reached at stored 30, never at
stored 3. And a thread is never shown above its owner's level: a level-4 character's
threads stop at stored 40.

Ysmay imbues through the real telnet path: ``ritual Rite of Imbuing`` then
``imbue thread=<id> amount=<n>``. The expected numbers come from the rules the magic
docs state: from stored level L the next level costs ``max((L - 9) x 100, 1)``
development points; each tenth stored level is an XP boundary the thread must have
paid for (paid up front here, so only resonance gates the imbue); the level cap is
character level x 10; the effective cap is the lower of that and the anchor cap.
"""

from __future__ import annotations

from integration_tests.harness import JourneyCase
from world.action_points.models import ActionPointConfig, ActionPointPool
from world.classes.factories import CharacterClassFactory
from world.classes.services import set_primary_class_level
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterAuraFactory,
    CharacterResonanceFactory,
    ImbuingRitualFactory,
    ResonanceFactory,
    ThreadFactory,
)
from world.magic.models import (
    CharacterResonance,
    Thread,
    ThreadLevelUnlock,
)
from world.magic.models.crossing import CrossingChoice, PendingCrossingOffer


def imbue_cost(start: int, end: int) -> int:
    """Development points to carry a thread from stored ``start`` to stored ``end``."""
    return sum(max((level - 9) * 100, 1) for level in range(start, end))


class _ThreadCase(JourneyCase):
    """Ysmay, in a quiet room, with resonance to spend and the Rite of Imbuing known."""

    def setUp(self) -> None:
        super().setUp()
        ActionPointConfig.objects.update_or_create(
            name="Default", defaults={"is_active": True, "weekly_regen": 80}
        )
        ImbuingRitualFactory()
        self.room = self.make_room("The Loom Room")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.sheet = self.ysmay.sheet_data
        CharacterAuraFactory(character=self.sheet)
        self.resonance = ResonanceFactory()
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance, balance=0)
        pool = ActionPointPool.get_or_create_for_character(self.ysmay)
        pool.current = 500
        pool.maximum = 500
        pool.save()

    # -- setup the story assumes --------------------------------------------

    def her_level_is(self, level: int) -> None:
        set_primary_class_level(self.ysmay, CharacterClassFactory(), level)

    def boundaries_paid(self, thread: Thread, up_to: int) -> None:
        """The XP boundaries on the way to stored ``up_to`` are already bought."""
        for boundary in range(10, up_to + 1, 10):
            ThreadLevelUnlock.objects.get_or_create(
                thread=thread, unlocked_level=boundary, defaults={"xp_spent": 0}
            )

    def fund(self, amount: int) -> None:
        row = CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.resonance)
        row.balance = amount
        row.save(update_fields=["balance"])

    def trait_thread(self, level: int, *, trait_value: int = 200) -> Thread:
        return ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            level=level,
            developed_points=0,
            _trait_value=trait_value,
        )

    # -- what she types ------------------------------------------------------

    def imbue(self, thread: Thread, amount: int) -> str:
        self.fund(amount)
        self.telnet(self.ysmay, "ritual Rite of Imbuing")
        told = self.telnet(self.ysmay, f"imbue thread={thread.pk} amount={amount}")
        thread.refresh_from_db()
        return told

    def crossing_list(self) -> str:
        return self.telnet(self.ysmay, "threads crossing list")


class ACrossingArrivesAtShownThree(_ThreadCase):
    def test_imbuing_to_stored_thirty_offers_the_level_three_crossing(self) -> None:
        """Stored 29 -> 30 is shown 2.9 -> 3: the crossing catalog offers level 3."""
        self.her_level_is(3)
        thread = self.trait_thread(29)
        self.boundaries_paid(thread, 30)

        told = self.imbue(thread, imbue_cost(29, 30))

        self.assertIn(f"You complete the rite, imbuing {thread.name}.", told)
        self.assertEqual(thread.level, 30)
        self.assertIn("Crossing level 3", self.crossing_list())
        self.assertTrue(
            PendingCrossingOffer.objects.filter(thread=thread, crossing_level=3).exists()
        )

    def test_stored_three_is_shown_point_three_and_offers_nothing(self) -> None:
        """Stored 2 -> 3 is shown 0.2 -> 0.3: no crossing fires."""
        thread = self.trait_thread(2)

        self.imbue(thread, imbue_cost(2, 3))

        self.assertEqual(thread.level, 3)
        self.assertIn("You have no pending crossing offers.", self.crossing_list())
        self.assertFalse(PendingCrossingOffer.objects.filter(thread=thread).exists())


class OneImbueAcrossTwoCrossings(_ThreadCase):
    def test_the_skipped_crossing_auto_resolves_and_the_highest_is_offered(self) -> None:
        """Stored 25 -> 62 passes shown 3 and 6: 3 takes its default, 6 is offered."""
        from world.conditions.factories import ConditionTemplateFactory
        from world.magic.models.crossing import CrossingOption

        default_at_three = CrossingOption.objects.create(
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            crossing_level=3,
            name="Steady Hand",
            condition_template=ConditionTemplateFactory(),
            is_default=True,
        )
        self.her_level_is(7)
        thread = self.trait_thread(25)
        self.boundaries_paid(thread, 60)

        self.imbue(thread, imbue_cost(25, 62))

        self.assertEqual(thread.level, 62)
        choice = CrossingChoice.objects.get(thread=thread)
        self.assertEqual((choice.crossing_level, choice.option), (3, default_at_three))
        told = self.crossing_list()
        self.assertIn("Crossing level 6", told)
        self.assertNotIn("Crossing level 3", told)


class TheThreadStopsAtHerLevel(_ThreadCase):
    def test_a_level_four_character_stops_at_stored_forty(self) -> None:
        """Level 4 caps every thread at stored 40 (shown 4), whatever the anchor allows."""
        from actions.definitions.imbue import ImbueAction

        self.her_level_is(4)
        thread = self.trait_thread(39, trait_value=200)
        self.boundaries_paid(thread, 50)
        self.fund(imbue_cost(39, 45))
        self.telnet(self.ysmay, "ritual Rite of Imbuing")

        outcome = self.web(self.ysmay, ImbueAction.key, thread=thread, amount=imbue_cost(39, 45))

        result = outcome.detail.data["result"]
        self.assertEqual((result.new_level, result.blocked_by), (40, "LEVEL_CAP"))

        told = self.imbue(thread, 100)
        self.assertIn("Your character level limits this thread's growth.", told)
        self.assertEqual(thread.level, 40)


class AnOrganizationThreadTakesTheLowerCap(_ThreadCase):
    def _org_thread(self, level: int) -> Thread:
        from world.magic.factories import GiftFactory
        from world.societies.factories import OrganizationFactory
        from world.societies.models import OrganizationGiftGrant

        org = OrganizationFactory()
        gift = GiftFactory()
        gift.resonances.add(self.resonance)
        OrganizationGiftGrant.objects.create(organization=org, gift=gift, anchor_cap=30)
        thread = Thread.objects.create(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.ORGANIZATION,
            target_organization=org,
            level=level,
        )
        self.boundaries_paid(thread, 40)
        return thread

    def test_her_level_binds_below_the_grant(self) -> None:
        """Grant 30, level 2: the thread stops at stored 20, held by her level."""
        self.her_level_is(2)
        thread = self._org_thread(19)

        self.imbue(thread, imbue_cost(19, 25))
        self.assertEqual(thread.level, 20)
        self.assertIn("Your character level limits this thread's growth.", self.imbue(thread, 100))

    def test_the_grant_binds_below_her_level(self) -> None:
        """Grant 30, level 5: the thread stops at stored 30, held by the grant."""
        self.her_level_is(5)
        thread = self._org_thread(29)

        self.imbue(thread, imbue_cost(29, 35))
        self.assertEqual(thread.level, 30)
        self.assertIn(
            "This thread cannot grow beyond its anchor's strength.", self.imbue(thread, 100)
        )


class TheSubRoleTakesOverAtShownThree(_ThreadCase):
    def test_a_role_thread_imbued_to_stored_thirty_resolves_the_level_three_sub_role(self) -> None:
        from world.covenants.constants import CovenantType
        from world.covenants.factories import (
            CharacterCovenantRoleFactory,
            CovenantFactory,
            CovenantRoleFactory,
            SubroleCovenantRoleFactory,
        )
        from world.magic.specialization.services import resolve_specialized_variant

        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        sub_role = SubroleCovenantRoleFactory(
            parent_role=role, resonance=self.resonance, unlock_thread_level=3
        )
        # A level-3 covenant gives the role thread an anchor cap of 30.
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant=CovenantFactory(covenant_type=CovenantType.DURANCE, level=3),
            covenant_role=role,
        )
        self.her_level_is(3)
        thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role=role,
            target_trait=None,
            level=29,
        )
        self.boundaries_paid(thread, 30)
        self.ysmay.threads.invalidate()
        self.assertEqual(resolve_specialized_variant(entity=role, character=self.ysmay), role)

        self.imbue(thread, imbue_cost(29, 30))

        self.assertEqual(thread.level, 30)
        self.ysmay.threads.invalidate()
        self.assertEqual(resolve_specialized_variant(entity=role, character=self.ysmay), sub_role)


class ASignatureFlourishWaitsForShownThree(_ThreadCase):
    def test_a_level_three_flourish_is_locked_at_stored_five_and_open_at_thirty(self) -> None:
        from world.magic.factories import (
            CharacterTechniqueFactory,
            SignatureMotifBonusFactory,
            TechniqueFactory,
        )
        from world.magic.services.technique_personalization import (
            seed_motif_from_gift_resonance,
        )

        technique = TechniqueFactory(level=3, name="Frost Lash")
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        seed_motif_from_gift_resonance(self.sheet, self.resonance)
        bonus = SignatureMotifBonusFactory(
            name="Rime Trail", required_resonance=self.resonance, min_crossing_level=3
        )
        self.her_level_is(3)
        thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.TECHNIQUE,
            target_technique=technique,
            target_trait=None,
            level=5,
        )
        self.boundaries_paid(thread, 30)
        self.ysmay.threads.invalidate()
        sign = "signature set technique=Frost Lash bonus=Rime Trail"

        self.assertIn(
            "That signature bonus requires a deeper thread. Keep imbuing.",
            self.telnet(self.ysmay, sign),
        )

        self.imbue(thread, imbue_cost(5, 30))
        self.assertEqual(thread.level, 30)
        self.ysmay.threads.invalidate()

        self.assertIn(f"Signature bonus '{bonus.name}' set on", self.telnet(self.ysmay, sign))
        thread.refresh_from_db()
        self.assertEqual(thread.signature_bonus, bonus)
