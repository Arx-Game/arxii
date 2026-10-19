"""Journeys through a GM's adjudication at the table (#3657, tranche 7).

Ravenna runs a scene at the Long Table. From her seat she calls an impromptu
check on a player, rewards one by fiat, and marks or clears a condition, each
typed as ``gm check``, ``gm award`` and ``gm condition`` through the command
handler, or sent as the GM panel sends it. Each journey asserts what the GM
was told, what the room heard, and what the rows hold. The die is pinned
(``ROLL_WELL``) wherever a check is rolled: the roll is the one thing a journey
cannot drive and still be a journey.

The one invariant every verb here keeps (ratified on #2118): a GM never invents
a check, a number or a consequence. Every line resolves against an authored
catalog row, and a kwarg shaped like an invention is ignored.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from evennia.objects.models import ObjectDB

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from integration_tests.harness import JourneyCase
from world.achievements.constants import AccessChangeSource
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory, CheckTypeTraitFactory
from world.classes.models import PathStage
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.models import ConditionInstance, ConditionTemplate
from world.conditions.services import get_active_conditions
from world.currency.models import FavorTokenDetails
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.gm.models import GMProfile
from world.magic.constants import AcquisitionOrigin, GiftKind, TargetKind
from world.magic.factories import (
    GiftFactory,
    ResonanceFactory,
    TechniqueFactory,
    UltimateTechniqueFactory,
)
from world.magic.models import CharacterGift, CharacterTechnique, Thread
from world.mechanics.models import ModifierTarget
from world.narrative.models import NarrativeMessage
from world.progression.models import (
    DevelopmentPoints,
    ExperiencePointsData,
    MaturationStatCap,
    XPTransaction,
)
from world.progression.types import ProgressionReason
from world.scenes.action_constants import DifficultyChoice
from world.scenes.constants import InteractionMode, InteractionVisibility
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Interaction, Scene
from world.scenes.narrator import NARRATOR_PERSONA_NAME
from world.societies.factories import OrganizationFactory
from world.species.factories import make_language_with_target, make_understanding_condition
from world.species.language_services import comprehension_value
from world.traits.constants import STAT_DISPLAY_DIVISOR
from world.traits.factories import CheckSystemSetupFactory, TraitFactory
from world.traits.models import (
    CharacterTraitChange,
    CharacterTraitValue,
    CheckRank,
    PointConversionRange,
    TraitCategory,
    TraitChangeSource,
    TraitType,
)

# A roll of 95 lands in the top band of every chart CheckSystemSetupFactory builds.
ROLL_WELL = patch("world.checks.services.random.randint", return_value=95)

CHECK_USAGE = "Usage: gm check [find <term>] | gm check <character> <check-type>=<band>"
AWARD_USAGE = "Usage: gm award <character> xp=<amount> [reason=<text>]"
CONDITION_USAGE = "Usage: gm condition <character> condition=<name> [severity=<n>] [duration=<n>]"
NO_SUCH_CHECK = "No such check -- try `gm check find <term>`."
PICK_A_BAND = "Pick a difficulty band: trivial, easy, normal, hard, daunting, harrowing."
NOT_THE_GM = "Only the scene's GM or staff can do that."


def check_system_with_ranks() -> None:
    """Outcomes and charts for the roll, plus the point conversion and ranks a
    check weighted on a stat reads when it turns the stat into points."""
    CheckSystemSetupFactory.create()
    PointConversionRange.objects.get_or_create(
        trait_type=TraitType.STAT,
        min_value=1,
        defaults={"max_value": 100, "points_per_level": 1},
    )
    for rank, min_points, name in ((0, 0, "Untried"), (1, 10, "Novice"), (2, 25, "Competent")):
        CheckRank.objects.get_or_create(
            rank=rank, defaults={"min_points": min_points, "name": name}
        )


def outcome_lines(scene: Scene) -> list[str]:
    """The Narrator's outcome lines in the scene's feed, oldest first."""
    rows = Interaction.objects.filter(scene=scene, mode=InteractionMode.OUTCOME).order_by("pk")
    return list(rows.values_list("content", flat=True))


def carried(bearer: ObjectDB, template: ConditionTemplate) -> ConditionInstance | None:
    """The active instance of ``template`` on ``bearer``, if any (the GM panel's own read)."""
    return get_active_conditions(bearer, condition=template).first()


def xp_earned(account: object) -> int:
    """What the ledger holds for the account (``0`` before any award)."""
    return (
        ExperiencePointsData.objects.filter(account=account)
        .values_list("total_earned", flat=True)
        .first()
        or 0
    )


def has_a_number(text: str) -> bool:
    return any(ch.isdigit() for ch in text)


class _TheLongTable(JourneyCase):
    """Ravenna runs a scene at the Long Table; Ysmay and Hobb play at it."""

    gm_level = GMLevel.JUNIOR

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Long Table")
        self.ravenna = self.make_player("Ravenna", room=self.room)
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        GMProfileFactory(account=self.account_of(self.ravenna), level=self.gm_level)
        self.scene = SceneFactory(room=self.room)
        SceneParticipationFactory(
            scene=self.scene, account=self.account_of(self.ravenna), is_gm=True
        )
        SceneParticipationFactory(scene=self.scene, account=self.account_of(self.ysmay))
        self.hobb_seat = SceneParticipationFactory(
            scene=self.scene, account=self.account_of(self.hobb)
        )
        self.watch(self.ysmay, self.hobb)

    def staff(self, name: str = "Dagny") -> ObjectDB:
        """A staffer standing in the room, with no GM profile and no seat in the scene."""
        character = self.make_player(name, room=self.room)
        account = self.account_of(character)
        account.is_staff = True
        account.save(update_fields=["is_staff"])
        return character

    def seat_hobb_as_gm(self, level: str) -> GMProfile:
        """Hobb takes a GM's seat at this scene, holding the given trust."""
        profile = GMProfileFactory(account=self.account_of(self.hobb), level=level)
        self.hobb_seat.is_gm = True
        self.hobb_seat.save(update_fields=["is_gm"])
        return profile

    def junior_gm_without_a_seat(self, name: str = "Tam") -> ObjectDB:
        """An approved GM in the room who is not running this scene."""
        character = self.make_player(name, room=self.room)
        GMProfileFactory(account=self.account_of(character), level=GMLevel.JUNIOR)
        return character


class CallingAnImpromptuCheck(_TheLongTable):
    """Ravenna, a Senior GM, calls a catalog check on Ysmay for a moment no situation covers.

    The result is graded and number-free and reaches Ravenna alone: nothing is
    written to the feed and nobody at the table hears it. A GM below Senior
    trust is sent to ``setsituation`` instead (ADR-0110).
    """

    gm_level = GMLevel.SENIOR

    def setUp(self) -> None:
        super().setUp()
        check_system_with_ranks()
        self.senses = TraitFactory(
            name="Senses", trait_type=TraitType.STAT, category=TraitCategory.PHYSICAL
        )
        self.tracking = CheckTypeFactory(
            name="Tracking",
            category=CheckCategoryFactory(name="Wilderness"),
            description="Follow a trail across country.",
        )
        CheckTypeTraitFactory(check_type=self.tracking, trait=self.senses, weight=Decimal("1.0"))
        CharacterTraitValue.objects.create(
            character=self.ysmay.sheet_data, trait=self.senses, value=30
        )

    def test_she_browses_the_catalog_and_calls_a_check_only_she_hears(self) -> None:
        row = f"[{self.tracking.pk}] Tracking"
        self.assertIn(row, self.telnet(self.ravenna, "gm check find track"))
        self.assertIn(row, self.telnet(self.ravenna, "gm check find Senses"))
        self.assertIn("Check catalog:", self.telnet(self.ravenna, "gm check"))
        self.assertIn(
            "No checks matched 'flying'.", self.telnet(self.ravenna, "gm check find flying")
        )

        with ROLL_WELL:
            told = self.telnet(self.ravenna, "gm check Ysmay Tracking=hard")
        self.assertIn("Ysmay: Tracking (Hard) -> ", told)
        self.assertFalse(has_a_number(told), told)
        self.assertNotTold(self.ysmay, "Tracking")
        self.assertNotTold(self.hobb, "Tracking")
        self.assertEqual(outcome_lines(self.scene), [])

        with ROLL_WELL:
            told = self.telnet(self.ravenna, f"gm check Ysmay {self.tracking.pk}=normal")
        self.assertIn("Ysmay: Tracking (Normal) -> ", told)

    def test_every_band_reads_back_as_a_word(self) -> None:
        for band in DifficultyChoice.values:
            with ROLL_WELL:
                told = self.telnet(self.ravenna, f"gm check Ysmay Tracking={band}")
            self.assertIn(f"Ysmay: Tracking ({DifficultyChoice(band).label}) -> ", told)
            self.assertFalse(has_a_number(told), told)

    def test_an_edge_or_a_setback_moves_the_band_one_step_with_its_reason(self) -> None:
        with ROLL_WELL:
            told = self.telnet(
                self.ravenna, "gm check Ysmay Tracking=hard edge=an ally braces the ladder"
            )
        self.assertIn(
            "Ysmay: Tracking (Hard) [edge -> Normal: an ally braces the ladder] -> ", told
        )
        with ROLL_WELL:
            told = self.telnet(
                self.ravenna, "gm check Ysmay Tracking=hard setback=the footing is treacherous"
            )
        self.assertIn(
            "Ysmay: Tracking (Hard) [setback -> Daunting: the footing is treacherous] -> ", told
        )
        self.assertIn(
            "Shift with edge or setback, not both.",
            self.telnet(self.ravenna, "gm check Ysmay Tracking=hard edge=help setback=hindrance"),
        )
        self.assertIn(
            "Already at the easiest band.",
            self.telnet(self.ravenna, "gm check Ysmay Tracking=trivial edge=help"),
        )
        self.assertIn(
            "Already at the hardest band.",
            self.telnet(self.ravenna, "gm check Ysmay Tracking=harrowing setback=hindrance"),
        )

    def test_what_the_line_refuses(self) -> None:
        self.assertIn(CHECK_USAGE, self.telnet(self.ravenna, "gm check Ysmay"))
        self.assertIn(
            "No character named 'Nobody' here.",
            self.telnet(self.ravenna, "gm check Nobody Tracking=hard"),
        )
        self.assertIn(NO_SUCH_CHECK, self.telnet(self.ravenna, "gm check Ysmay Flying=hard"))
        self.assertIn(PICK_A_BAND, self.telnet(self.ravenna, "gm check Ysmay Tracking=60"))

    def test_only_a_senior_gm_or_staff_calls_one(self) -> None:
        self.assertIn("GM trust required.", self.telnet(self.hobb, "gm check Ysmay Tracking=hard"))
        self.assertIn("GM trust required.", self.telnet(self.hobb, "gm check find track"))

        profile = self.seat_hobb_as_gm(GMLevel.JUNIOR)
        senior_only = "Requires Senior GM or higher."
        self.assertIn(senior_only, self.telnet(self.hobb, "gm check Ysmay Tracking=hard"))
        self.assertIn(senior_only, self.telnet(self.hobb, "gm check find track"))
        profile.level = GMLevel.STARTING
        profile.save(update_fields=["level"])
        self.assertIn(senior_only, self.telnet(self.hobb, "gm check Ysmay Tracking=hard"))

        dagny = self.staff()
        with ROLL_WELL:
            told = self.telnet(dagny, "gm check Ysmay Tracking=hard")
        self.assertIn("Ysmay: Tracking (Hard) -> ", told)

    def test_the_web_names_her_by_id_and_ignores_an_invented_number(self) -> None:
        with ROLL_WELL:
            called = self.web(
                self.ravenna,
                "gm_invoke_check",
                target=self.ysmay.pk,
                check_type_ref="Tracking",
                difficulty="hard",
            )
        self.assertTrue(called.detail.success, called.detail.message)
        self.assertIn("Ysmay: Tracking (Hard) -> ", called.detail.message)

        nobody = self.web(
            self.ravenna,
            "gm_invoke_check",
            target=999999999,
            check_type_ref="Tracking",
            difficulty="hard",
        )
        self.assertFalse(nobody.detail.success)
        self.assertIn("No such target.", nobody.detail.message)

        numbered = self.web(
            self.ravenna,
            "gm_invoke_check",
            target=self.ysmay.pk,
            check_type_ref="Tracking",
            difficulty=60,
        )
        self.assertFalse(numbered.detail.success)
        self.assertIn(PICK_A_BAND, numbered.detail.message)

        # A stat, a skill, a pool and an empty edge: none of them is read.
        with ROLL_WELL:
            extras = self.web(
                self.ravenna,
                "gm_invoke_check",
                target=self.ysmay.pk,
                check_type_ref="Tracking",
                difficulty="trivial",
                stat="strength",
                skill="athletics",
                consequence_pool_id=999,
                consequence_pool="whatever",
                edge_reason="",
            )
        self.assertTrue(extras.detail.success, extras.detail.message)
        self.assertIn("Ysmay: Tracking (Trivial) -> ", extras.detail.message)
        self.assertNotIn("edge", extras.detail.message)


class RewardingAPlayerByFiat(_TheLongTable):
    """Ravenna, a Junior GM, rewards Ysmay from her seat: XP, development, a Golden
    Hare, a stat and a technique, each written with the GM's own name on it."""

    def setUp(self) -> None:
        super().setUp()
        self.lockpicking = TraitFactory(name="Lockpicking", trait_type=TraitType.SKILL)
        self.brawn = TraitFactory(
            name="Brawn", trait_type=TraitType.STAT, category=TraitCategory.PHYSICAL
        )

    def test_xp_lands_on_her_account_with_the_reason_on_the_ledger(self) -> None:
        told = self.telnet(self.ravenna, "gm award Ysmay xp=15 reason=heroic rescue")
        self.assertIn("Awarded 15 XP to Ysmay.", told)
        account = self.account_of(self.ysmay)
        self.assertEqual(xp_earned(account), 15)
        entry = XPTransaction.objects.get(account=account)
        self.assertEqual(entry.reason, ProgressionReason.GM_AWARD)
        self.assertEqual(entry.gm, self.account_of(self.ravenna))
        self.assertEqual(entry.description, "heroic rescue")
        self.assertEqual(entry.character_id, self.ysmay.sheet_data.pk)

        not_a_count = "amount must be a positive whole number."
        self.assertIn(not_a_count, self.telnet(self.ravenna, "gm award Ysmay xp=0"))
        self.assertIn(not_a_count, self.telnet(self.ravenna, "gm award Ysmay xp=lots"))
        self.assertEqual(xp_earned(account), 15)

    def test_development_points_name_a_trait_and_an_amount(self) -> None:
        told = self.telnet(
            self.ravenna, "gm award Ysmay dev=Lockpicking amount=5 reason=training montage"
        )
        self.assertIn("Awarded 5 development point(s) in Lockpicking to Ysmay.", told)
        points = DevelopmentPoints.objects.get(
            character_sheet=self.ysmay.sheet_data, trait=self.lockpicking
        )
        self.assertEqual(points.total_earned, 5)
        self.assertIn(
            "amount must be a positive whole number.",
            self.telnet(self.ravenna, "gm award Ysmay dev=Lockpicking"),
        )
        self.assertIn(
            "No trait named 'Juggling'.",
            self.telnet(self.ravenna, "gm award Ysmay dev=Juggling amount=5"),
        )

    def test_a_golden_hare_is_minted_for_a_deed_she_names(self) -> None:
        academy = OrganizationFactory(name="The Golden Hare Academy")
        told = self.telnet(
            self.ravenna,
            "gm award Ysmay hare=The Golden Hare Academy reason=Cleared the Thornwood ambush",
        )
        self.assertIn("Minted a Golden Hare from The Golden Hare Academy for Ysmay.", told)
        token = FavorTokenDetails.objects.get(issuing_organization=academy)
        self.assertEqual(token.provenance_note, "Cleared the Thornwood ambush")
        self.assertEqual(token.item_instance.holder_character_sheet_id, self.ysmay.sheet_data.pk)

        self.assertIn(
            "A description of the deed is required to mint a Golden Hare.",
            self.telnet(self.ravenna, f"gm award Ysmay hare={academy.pk}"),
        )
        self.assertIn(
            "No organization named 'Nonexistent Order'.",
            self.telnet(self.ravenna, "gm award Ysmay hare=Nonexistent Order reason=a deed"),
        )
        self.assertEqual(FavorTokenDetails.objects.count(), 1)

        # A deed told at length is kept to the note's width, not refused by the database.
        told = self.telnet(self.ravenna, f"gm award Ysmay hare={academy.pk} reason={'x' * 250}")
        self.assertIn("Minted a Golden Hare from The Golden Hare Academy for Ysmay.", told)
        notes = FavorTokenDetails.objects.order_by("pk").values_list("provenance_note", flat=True)
        self.assertEqual(list(notes), ["Cleared the Thornwood ambush", "x" * 200])

    def test_a_stat_rises_one_dot_in_her_gm_s_name(self) -> None:
        self.assertIn(
            "Raised Brawn to 1 for Ysmay.", self.telnet(self.ravenna, "gm award Ysmay stat=Brawn")
        )
        value = CharacterTraitValue.objects.get(character=self.ysmay.sheet_data, trait=self.brawn)
        self.assertEqual(value.value, STAT_DISPLAY_DIVISOR)
        change = CharacterTraitChange.objects.get(
            character_sheet=self.ysmay.sheet_data, trait=self.brawn
        )
        self.assertEqual(change.source, TraitChangeSource.GM_GRANT)
        self.assertEqual((change.old_value, change.new_value), (0, STAT_DISPLAY_DIVISOR))
        self.assertEqual(
            change.granting_tenure, self.ravenna.sheet_data.roster_entry.current_tenure
        )

        self.assertIn(
            "Only stat traits can be raised by a GM story reward.",
            self.telnet(self.ravenna, "gm award Ysmay stat=Lockpicking"),
        )
        self.assertFalse(CharacterTraitChange.objects.filter(trait=self.lockpicking).exists())

        MaturationStatCap.objects.create(path_stage=PathStage.PROSPECT, stat_cap=1)
        self.assertIn(
            "Brawn is already at the maximum Ysmay's stage allows.",
            self.telnet(self.ravenna, "gm award Ysmay stat=Brawn"),
        )
        self.assertEqual(
            CharacterTraitValue.objects.get(
                character=self.ysmay.sheet_data, trait=self.brawn
            ).value,
            STAT_DISPLAY_DIVISOR,
        )

    def test_a_technique_is_granted_from_a_gift_she_holds(self) -> None:
        gift = GiftFactory(name="Emberwork", kind=GiftKind.MINOR)
        resonance = ResonanceFactory()
        gift.resonances.add(resonance)
        technique = TechniqueFactory(gift=gift, name="Ember Lance")

        self.assertIn(
            "Ysmay does not hold the Emberwork gift.",
            self.telnet(self.ravenna, "gm award Ysmay technique=Ember Lance"),
        )
        self.assertFalse(CharacterTechnique.objects.exists())

        CharacterGift.objects.create(character=self.ysmay.sheet_data, gift=gift)
        Thread.objects.create(
            owner=self.ysmay.sheet_data,
            resonance=resonance,
            target_kind=TargetKind.GIFT,
            target_gift=gift,
            level=0,
        )
        told = self.telnet(self.ravenna, "gm award Ysmay technique=Ember Lance")
        self.assertIn("Granted Ember Lance to Ysmay.", told)
        known = CharacterTechnique.objects.get(character=self.ysmay.sheet_data)
        self.assertEqual((known.technique, known.origin), (technique, AcquisitionOrigin.GM_GRANT))
        self.assertIn(AccessChangeSource.GM_AWARD.label, NarrativeMessage.objects.latest("id").body)

        self.assertIn(
            "already knows Ember Lance.",
            self.telnet(self.ravenna, "gm award Ysmay technique=Ember Lance"),
        )
        UltimateTechniqueFactory(gift=gift, name="Sunfall")
        self.assertIn(
            "That technique can only be used in Audere.",
            self.telnet(self.ravenna, "gm award Ysmay technique=Sunfall"),
        )
        self.assertIn(
            "No technique named 'Moonfall'.",
            self.telnet(self.ravenna, "gm award Ysmay technique=Moonfall"),
        )
        self.assertEqual(
            CharacterTechnique.objects.filter(character=self.ysmay.sheet_data).count(), 1
        )

    def test_the_usage_and_who_may_award(self) -> None:
        self.assertIn(AWARD_USAGE, self.telnet(self.ravenna, "gm award"))
        self.assertIn(AWARD_USAGE, self.telnet(self.ravenna, "gm award Ysmay"))
        self.assertIn(AWARD_USAGE, self.telnet(self.ravenna, "gm award Ysmay legend=5"))
        self.assertIn(
            "No character named 'Nobody' here.", self.telnet(self.ravenna, "gm award Nobody xp=5")
        )

        self.assertIn("GM trust required.", self.telnet(self.hobb, "gm award Ysmay xp=5"))
        self.seat_hobb_as_gm(GMLevel.STARTING)
        self.assertIn(
            "Requires Junior GM or higher.", self.telnet(self.hobb, "gm award Ysmay xp=5")
        )
        tam = self.junior_gm_without_a_seat()
        self.assertIn(NOT_THE_GM, self.telnet(tam, "gm award Ysmay xp=5"))
        self.assertEqual(xp_earned(self.account_of(self.ysmay)), 0)

        self.assertIn("Awarded 5 XP to Ysmay.", self.telnet(self.staff(), "gm award Ysmay xp=5"))

    def test_the_web_awards_by_id_and_a_staffer_with_no_tenure_still_signs(self) -> None:
        awarded = self.web(
            self.ravenna, "gm_award_progression", target=self.ysmay.pk, award_type="xp", amount=10
        )
        self.assertTrue(awarded.detail.success, awarded.detail.message)
        self.assertEqual(xp_earned(self.account_of(self.ysmay)), 10)

        unknown = self.web(
            self.ravenna,
            "gm_award_progression",
            target=self.ysmay.pk,
            award_type="legend",
            amount=5,
        )
        self.assertFalse(unknown.detail.success)
        self.assertIn(
            "award_type must be one of: xp, development, favor_token, stat, technique.",
            unknown.detail.message,
        )
        nobody = self.web(
            self.ravenna, "gm_award_progression", target=999999999, award_type="xp", amount=5
        )
        self.assertFalse(nobody.detail.success)
        self.assertIn("A target character is required.", nobody.detail.message)

        # A staffer piloting a character with no roster tenure still makes the grant;
        # the change simply carries no granting tenure.
        warden = CharacterFactory(db_key="Warden", location=self.room)
        CharacterSheetFactory(character=warden)
        warden.db_account = AccountFactory(username="warden_staff", is_staff=True)
        warden.save()
        raised = self.web(
            warden,
            "gm_award_progression",
            target=self.ysmay.pk,
            award_type="stat",
            trait_ref="Brawn",
        )
        self.assertTrue(raised.detail.success, raised.detail.message)
        change = CharacterTraitChange.objects.get(
            character_sheet=self.ysmay.sheet_data, trait=self.brawn
        )
        self.assertIsNone(change.granting_tenure)


class MarkingAndClearingACondition(_TheLongTable):
    """Ravenna, a Junior GM, marks Ysmay with an authored condition and clears it again.

    Her note, when she gives one, is the Narrator's line to the room, or to the
    bearer alone when others cannot see the condition; without a note nothing is
    said. A prop can bear a condition too, named on the web by its id (the typed
    line names characters only).
    """

    def setUp(self) -> None:
        super().setUp()
        self.fever = ConditionTemplateFactory(name="Marsh Fever")
        self.brand = ConditionTemplateFactory(name="Marked", is_visible_to_others=False)

    def test_her_note_is_narrated_to_the_room_and_kept_on_the_instance(self) -> None:
        told = self.telnet(
            self.ravenna, "gm condition Ysmay condition=Marsh Fever note=The wine was poisoned."
        )
        self.assertIn("Ysmay is now Marsh Fever.", told)
        line = "Ysmay is now Marsh Fever. The wine was poisoned."
        self.assertTold(self.ysmay, line)
        self.assertTold(self.hobb, line)
        self.assertEqual(outcome_lines(self.scene), [line])
        outcome = Interaction.objects.get(mode=InteractionMode.OUTCOME)
        self.assertEqual(outcome.persona.name, NARRATOR_PERSONA_NAME)
        self.assertEqual(outcome.visibility, InteractionVisibility.DEFAULT)
        self.assertFalse(outcome.receivers.exists())

        fever = carried(self.ysmay, self.fever)
        self.assertIsNotNone(fever)
        self.assertEqual(
            (fever.severity, fever.rounds_remaining), (1, self.fever.default_duration_value)
        )
        self.assertEqual(fever.source_character, self.ravenna)
        self.assertEqual(fever.source_description, "The wine was poisoned.")

    def test_without_a_note_the_room_hears_nothing(self) -> None:
        told = self.telnet(
            self.ravenna, "gm condition Ysmay condition=Marsh Fever severity=3 duration=7"
        )
        self.assertIn("Ysmay is now Marsh Fever.", told)
        self.assertNotTold(self.ysmay, "Marsh Fever")
        self.assertNotTold(self.hobb, "Marsh Fever")
        self.assertEqual(outcome_lines(self.scene), [])
        fever = carried(self.ysmay, self.fever)
        self.assertEqual((fever.severity, fever.rounds_remaining), (3, 7))

    def test_a_hidden_condition_s_note_reaches_only_her(self) -> None:
        told = self.telnet(
            self.ravenna, "gm condition Ysmay condition=Marked note=A brand only you can feel."
        )
        self.assertIn("Ysmay is now Marked.", told)
        self.assertShownRow(self.ysmay, "Ysmay is now Marked. A brand only you can feel.")
        self.assertNotTold(self.hobb, "Marked")
        self.assertFalse([row for row in self.mailbox(self.hobb).rows if "Marked" in row])
        outcome = Interaction.objects.get(mode=InteractionMode.OUTCOME)
        self.assertEqual(outcome.visibility, InteractionVisibility.PERCEIVED_ONLY)
        self.assertEqual(
            list(outcome.receivers.values_list("persona_id", flat=True)),
            [self.ysmay.sheet_data.primary_persona.pk],
        )

    def test_what_the_line_refuses(self) -> None:
        self.assertIn(CONDITION_USAGE, self.telnet(self.ravenna, "gm condition"))
        self.assertIn(CONDITION_USAGE, self.telnet(self.ravenna, "gm condition Ysmay"))
        self.assertIn(CONDITION_USAGE, self.telnet(self.ravenna, "gm condition Ysmay severity=2"))
        self.assertIn(
            "No character named 'Nobody' here.",
            self.telnet(self.ravenna, "gm condition Nobody condition=Marsh Fever"),
        )
        self.assertIn(
            "No condition named 'Plague'.",
            self.telnet(self.ravenna, "gm condition Ysmay condition=Plague"),
        )
        self.assertIn(
            "severity must be a positive whole number.",
            self.telnet(self.ravenna, "gm condition Ysmay condition=Marsh Fever severity=0"),
        )
        self.assertIn(
            "duration_rounds must be a positive whole number.",
            self.telnet(self.ravenna, "gm condition Ysmay condition=Marsh Fever duration=-1"),
        )
        self.assertIsNone(carried(self.ysmay, self.fever))

    def test_she_lists_it_and_clears_it_with_a_reason(self) -> None:
        self.telnet(self.ravenna, "gm condition Ysmay condition=Marsh Fever severity=2 duration=5")
        listed = self.web(self.ravenna, "gm_list_conditions", target=self.ysmay.pk)
        self.assertTrue(listed.detail.success, listed.detail.message)
        rows = listed.detail.data["conditions"]
        self.assertEqual(
            [(row["name"], row["severity"], row["rounds_remaining"]) for row in rows],
            [("Marsh Fever", 2, 5)],
        )
        self.assertIn(f"[{rows[0]['id']}] Marsh Fever (severity 2)", listed.detail.message)

        self.assertIn(CONDITION_USAGE, self.telnet(self.ravenna, "gm condition remove"))
        self.assertIn(
            CONDITION_USAGE,
            self.telnet(self.ravenna, "gm condition remove Ysmay condition=Marsh Fever"),
        )
        self.assertIsNotNone(carried(self.ysmay, self.fever))

        told = self.telnet(
            self.ravenna, "gm condition remove Ysmay condition=Marsh Fever reason=the scene's over"
        )
        self.assertIn("Marsh Fever removed from Ysmay (the scene's over).", told)
        self.assertIsNone(carried(self.ysmay, self.fever))
        self.assertIn(
            "Ysmay does not have Marsh Fever active.",
            self.telnet(
                self.ravenna, "gm condition remove Ysmay condition=Marsh Fever reason=again"
            ),
        )
        self.assertIn(
            "No condition named 'Plague'.",
            self.telnet(self.ravenna, "gm condition remove Ysmay condition=Plague reason=gone"),
        )
        self.assertIn(
            "No character named 'Nobody' here.",
            self.telnet(
                self.ravenna, "gm condition remove Nobody condition=Marsh Fever reason=gone"
            ),
        )

        empty = self.web(self.ravenna, "gm_list_conditions", target=self.ysmay.pk)
        self.assertEqual(empty.detail.data["conditions"], [])
        self.assertIn("Ysmay has no active conditions.", empty.detail.message)
        unreasoned = self.web(
            self.ravenna, "gm_remove_condition", target=self.ysmay.pk, condition="Marsh Fever"
        )
        self.assertFalse(unreasoned.detail.success)
        self.assertIn("A reason is required to remove a condition.", unreasoned.detail.message)

    def test_only_a_junior_gm_at_the_table_or_staff_marks_anyone(self) -> None:
        mark = "gm condition Ysmay condition=Marsh Fever"
        clear = "gm condition remove Ysmay condition=Marsh Fever reason=enough"
        self.assertIn("GM trust required.", self.telnet(self.hobb, mark))
        self.seat_hobb_as_gm(GMLevel.STARTING)
        junior_only = "Requires Junior GM or higher."
        self.assertIn(junior_only, self.telnet(self.hobb, mark))
        self.assertIn(junior_only, self.telnet(self.hobb, clear))
        listed = self.web(self.hobb, "gm_list_conditions", target=self.ysmay.pk)
        self.assertFalse(listed.detail.success)
        self.assertIn(junior_only, listed.detail.message)
        tam = self.junior_gm_without_a_seat()
        self.assertIn(NOT_THE_GM, self.telnet(tam, mark))
        self.assertIsNone(carried(self.ysmay, self.fever))

        dagny = self.staff()
        self.assertIn("Ysmay is now Marsh Fever.", self.telnet(dagny, mark))
        self.assertIn("Marsh Fever removed from Ysmay (enough).", self.telnet(dagny, clear))
        self.assertIsNone(carried(self.ysmay, self.fever))

    def test_a_staffer_standing_nowhere_still_reaches_her(self) -> None:
        dagny = self.staff()
        dagny.location = None
        dagny.save()
        marked = self.web(
            dagny,
            "gm_apply_condition",
            target=self.ysmay.pk,
            condition_ref="Marsh Fever",
            note="The wine was poisoned.",
        )
        self.assertTrue(marked.detail.success, marked.detail.message)
        self.assertShownRow(self.ysmay, "Ysmay is now Marsh Fever. The wine was poisoned.")
        self.assertNotTold(self.hobb, "Marsh Fever")
        self.assertFalse([row for row in self.mailbox(self.hobb).rows if "Marsh Fever" in row])
        outcome = Interaction.objects.get(mode=InteractionMode.OUTCOME)
        self.assertIsNone(outcome.scene)
        self.assertEqual(outcome.visibility, InteractionVisibility.DEFAULT)
        self.assertFalse(outcome.receivers.exists())

    def test_a_prop_bears_a_condition_too(self) -> None:
        vase = ObjectDBFactory(db_key="Cracked Vase", location=self.room)
        marked = self.web(
            self.ravenna,
            "gm_apply_condition",
            target=vase.pk,
            condition_ref="Marsh Fever",
            note="It was cracked in the fall.",
        )
        self.assertTrue(marked.detail.success, marked.detail.message)
        self.assertIn("Cracked Vase is now Marsh Fever.", marked.detail.message)
        line = "Cracked Vase is now Marsh Fever. It was cracked in the fall."
        self.assertTold(self.hobb, line)
        self.assertEqual(outcome_lines(self.scene), [line])

        # A hidden condition on a prop has no bearer to tell: nothing is said or recorded.
        hidden = self.web(
            self.ravenna,
            "gm_apply_condition",
            target=vase.pk,
            condition_ref="Marked",
            note="Nobody will know.",
        )
        self.assertTrue(hidden.detail.success, hidden.detail.message)
        self.assertEqual(outcome_lines(self.scene), [line])
        self.assertNotTold(self.hobb, "Nobody will know.")
        self.assertIsNotNone(carried(vase, self.brand))

    def test_an_understanding_condition_opens_her_ear_to_a_tongue(self) -> None:
        # #4090: a condition whose effect raises comprehension of a language.
        ModifierTarget.clear_trait_cache()
        tongue, fluency = make_language_with_target("Old Marsh Tongue")
        make_understanding_condition("Tutored Ear", fluency)
        self.assertEqual(comprehension_value(self.ysmay.sheet_data, tongue), 0)
        self.assertIn(
            "Ysmay is now Tutored Ear.",
            self.telnet(self.ravenna, "gm condition Ysmay condition=Tutored Ear severity=4"),
        )
        self.assertEqual(comprehension_value(self.ysmay.sheet_data, tongue), 80)
