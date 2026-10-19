"""Journeys through a character's progression (#3657, tranche 12): ``journal``,
``goal``, ``kudos``, ``nominate``, ``randomscene``, ``pathintent``, ``rest``,
``training``, ``progression``, ``learn``, ``train``, ``tidings``, ``account`` and
``roster``.

Ysmay writes, plans, earns and spends; Hobb is the other player it involves. Each
journey types what a player types through the command handler and asserts what she
was told and what the rows hold.
"""

from __future__ import annotations

from allauth.account.models import EmailAddress
from django.core import mail
from django.test import override_settings
from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.action_points.models import ActionPointConfig, ActionPointPool
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.character_sheets.types import RetortConsent
from world.classes.factories import CharacterClassFactory, PathFactory
from world.fatigue.services import get_or_create_fatigue_pool
from world.game_clock.week_services import get_current_game_week
from world.goals.factories import GoalDomainFactory
from world.goals.models import CharacterGoal, GoalJournal
from world.journals.models import JournalEntry, WeeklyJournalXP
from world.magic.constants import GiftKind
from world.magic.factories import (
    GiftFactory,
    GiftUnlockFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueTeachingOfferFactory,
    ThreadWeavingTeachingOfferFactory,
)
from world.magic.models import CharacterGift, CharacterGiftUnlock, TechniqueProgress
from world.progression.factories import (
    CharacterPathHistoryFactory,
    ExperiencePointsDataFactory,
    KudosClaimCategoryFactory,
    KudosPointsDataFactory,
    RandomSceneTargetFactory,
)
from world.progression.models import (
    CharacterUnlock,
    ClassLevelUnlock,
    ClassXPCost,
    ExperiencePointsData,
    KudosPointsData,
    Nomination,
    XPCostChart,
    XPCostEntry,
)
from world.progression.models.path_intent import PathIntent
from world.room_features.models import RoomFeatureInstance
from world.room_features.seeds import ensure_notice_board_kind, ensure_town_crier_kind
from world.roster.factories import RosterApplicationFactory
from world.roster.models import RosterTenure
from world.roster.models.choices import ApplicationStatus
from world.scenes.models import Interaction, Persona
from world.secrets.factories import SecretFactory
from world.skills.factories import SkillFactory, SpecializationFactory
from world.skills.models import TrainingAllocation
from world.societies.factories import (
    LegendEntryFactory,
    SocietyFactory,
    SocietyReputationFactory,
)
from world.species.factories import LanguageFactory


def xp_of(case: JourneyCase, character) -> int:
    """The XP the account playing ``character`` can spend right now."""
    points = ExperiencePointsData.objects.filter(account=case.account_of(character)).first()
    return points.current_available if points else 0


def tenure_of(character) -> RosterTenure:
    return RosterTenure.objects.get(
        roster_entry__character_sheet=character.sheet_data, end_date__isnull=True
    )


class KeepingAJournal(JourneyCase):
    """Ysmay writes her journal; Hobb answers it, when she lets him."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)

    def test_an_entry_is_written_revised_and_answered(self) -> None:
        self.assertIn("You have written no journal entries.", self.telnet(self.ysmay, "journal"))

        told = self.telnet(
            self.ysmay,
            "journal write title=A Courtly Observation "
            "body=The Duke was severe today. public tags=court,rumor",
        )
        self.assertIn("You write a new journal entry: A Courtly Observation.", told)
        entry = JournalEntry.objects.get(author=self.ysmay.sheet_data)
        self.assertEqual(entry.title, "A Courtly Observation")
        self.assertEqual(entry.body, "The Duke was severe today.")
        self.assertTrue(entry.is_public)
        self.assertEqual({tag.name for tag in entry.tags.all()}, {"court", "rumor"})
        tracker = WeeklyJournalXP.objects.get(character_sheet=self.ysmay.sheet_data)
        self.assertEqual(tracker.posts_this_week, 1)
        self.assertEqual(xp_of(self, self.ysmay), 5)

        listed = strip_ansi(self.telnet(self.ysmay, "journal list"))
        self.assertIn(f"[#{entry.pk}] A Courtly Observation", listed)
        self.assertIn("Use 'journal edit <id>' to revise one.", listed)

        self.assertIn(
            "You revise 'A Courtly Remark'.",
            self.telnet(self.ysmay, f"journal edit #{entry.pk} title=A Courtly Remark"),
        )
        entry.refresh_from_db()
        self.assertEqual(entry.title, "A Courtly Remark")
        self.assertIsNotNone(entry.edited_at)
        self.assertIn(
            "Provide at least one of title, body or about to edit.",
            self.telnet(self.ysmay, f"journal edit {entry.pk}"),
        )
        self.assertIn("Usage: journal edit <id|#>", self.telnet(self.ysmay, "journal edit"))

        # Praise is open to anyone; a retort needs her leave or a rivalry.
        self.assertIn(
            "You respond to 'A Courtly Remark' with praise.",
            self.telnet(
                self.hobb,
                f"journal respond {entry.pk} type=praise title=Well Said body=I quite agree.",
            ),
        )
        praise = JournalEntry.objects.get(parent=entry, response_type="praise")
        self.assertEqual(praise.author_id, self.hobb.sheet_data.pk)
        self.assertEqual(praise.body, "I quite agree.")
        self.assertIn(
            "This entry is not available to respond to right now.",
            self.telnet(
                self.hobb, f"journal respond {entry.pk} type=retort title=Nonsense body=Not so."
            ),
        )
        self.assertIn(
            "Retorts and condemnation of your journals: anyone.",
            self.telnet(self.ysmay, "journal consent anyone"),
        )
        self.ysmay.sheet_data.refresh_from_db()
        self.assertEqual(self.ysmay.sheet_data.retort_consent, RetortConsent.ANYONE)
        self.assertIn(
            "You respond to 'A Courtly Remark' with retort.",
            self.telnet(
                self.hobb, f"journal respond {entry.pk} type=retort title=Nonsense body=Not so."
            ),
        )
        self.assertTrue(JournalEntry.objects.filter(parent=entry, response_type="retort").exists())

        self.assertIn(
            "Cannot respond to your own journal entry.",
            self.telnet(
                self.ysmay, f"journal respond {entry.pk} type=praise title=Me body=I agree with me."
            ),
        )
        self.assertIn(
            "That journal entry was not found.",
            self.telnet(self.hobb, "journal respond 99999 type=praise title=x body=y"),
        )
        self.assertIn(
            "Usage: journal respond <id|#> type=praise|retort|condemn title=<text> body=<text>",
            self.telnet(self.hobb, "journal respond"),
        )
        self.assertIn("body is required.", self.telnet(self.ysmay, "journal write title=Only"))
        self.assertIn("Usage: journal [list|write", self.telnet(self.ysmay, "journal frobnicate"))
        self.assertIn(
            "Usage: journal consent rivals|anyone", self.telnet(self.ysmay, "journal consent all")
        )

    def test_a_private_entry_stays_hers(self) -> None:
        self.telnet(self.ysmay, "journal write title=Secret Thoughts body=Hidden musings.")
        entry = JournalEntry.objects.get(author=self.ysmay.sheet_data)
        self.assertFalse(entry.is_public)
        self.assertIn(
            "Cannot respond to a private journal entry.",
            self.telnet(
                self.hobb, f"journal respond {entry.pk} type=praise title=Seen body=I saw it."
            ),
        )
        self.assertFalse(JournalEntry.objects.filter(parent=entry).exists())

        self.assertIn(
            "Your private journals will seal after death by default.",
            self.telnet(self.ysmay, "journal disposition sheet=seal"),
        )
        self.ysmay.sheet_data.refresh_from_db()
        self.assertEqual(self.ysmay.sheet_data.posthumous_journal_disposition, "seal")
        self.assertIn(
            "You revise 'Secret Thoughts'.",
            self.telnet(self.ysmay, f"journal disposition entry=#{entry.pk} value=reveal"),
        )
        entry.refresh_from_db()
        self.assertEqual(entry.posthumous_override, "reveal")
        self.assertIn(
            "Usage: journal disposition entry=<id> value=<inherit|reveal|seal>",
            self.telnet(self.ysmay, "journal disposition entry=x value=seal"),
        )
        self.assertIn("sheet is required.", self.telnet(self.ysmay, "journal disposition"))
        self.assertIn(
            "disposition must be reveal or seal.",
            self.telnet(self.ysmay, "journal disposition sheet=burn"),
        )


class SettingGoals(JourneyCase):
    """Ysmay allocates her goal points and logs what she did about them."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.standing = GoalDomainFactory(name="Standing")
        self.wealth = GoalDomainFactory(name="Wealth")

    def test_goals_are_set_logged_and_gated_for_a_week(self) -> None:
        told = strip_ansi(self.telnet(self.ysmay, "goal"))
        self.assertIn("Goals: 0/30 points allocated", told)
        self.assertIn("No goals set.", told)

        self.assertIn(
            "10 points allocated across 1 domains.",
            self.telnet(self.ysmay, "goal add domain=Standing points=10 notes=Gain standing"),
        )
        goal = CharacterGoal.objects.get(character=self.ysmay.sheet_data)
        self.assertEqual(
            (goal.domain_id, goal.points, goal.notes), (self.standing.pk, 10, "Gain standing")
        )
        told = strip_ansi(self.telnet(self.ysmay, "goal list"))
        self.assertIn("Goals: 10/30 points allocated", told)
        self.assertIn("[Standing] 10 pts", told)
        self.assertIn("Gain standing", told)

        # The weekly revision gate: the first write is free, the next waits a week.
        self.assertIn(
            "You cannot revise your goals again yet.",
            self.telnet(self.ysmay, f"goal add domain={self.wealth.pk} points=5"),
        )
        self.assertEqual(CharacterGoal.objects.filter(character=self.ysmay.sheet_data).count(), 1)

        self.assertIn(
            "You log progress: A step forward.",
            self.telnet(
                self.ysmay, "goal log domain=Standing title=A step forward content=Curried favor."
            ),
        )
        logged = GoalJournal.objects.get(character=self.ysmay.sheet_data)
        self.assertEqual((logged.domain_id, logged.content), (self.standing.pk, "Curried favor."))
        self.assertEqual(logged.xp_awarded, 1)
        self.assertEqual(xp_of(self, self.ysmay), 1)
        self.assertIn(
            "You log progress: Idle thoughts.",
            self.telnet(self.ysmay, "goal log title=Idle thoughts content=Nothing today. public"),
        )
        reflection = GoalJournal.objects.get(character=self.ysmay.sheet_data, title="Idle thoughts")
        self.assertIsNone(reflection.domain)
        self.assertTrue(reflection.is_public)

        self.assertIn(
            "No goal domain 'Bogus' found.",
            self.telnet(self.ysmay, "goal add domain=Bogus points=5"),
        )
        self.assertIn("content is required.", self.telnet(self.ysmay, "goal log title=Only"))
        self.assertIn(
            "Usage: goal set domain=<id>:points=<n>[,domain=<id>:points=<n>...]",
            self.telnet(self.ysmay, "goal set"),
        )
        self.assertIn(
            "points must be a number.",
            self.telnet(self.ysmay, f"goal set domain={self.standing.pk}:points=many"),
        )
        self.assertIn("Usage: goal [list|add", self.telnet(self.ysmay, "goal frobnicate"))

    def test_the_point_cap_holds(self) -> None:
        self.assertIn(
            "Total goal points exceed the maximum of 30.",
            self.telnet(
                self.ysmay,
                f"goal set domain={self.standing.pk}:points=20,domain={self.wealth.pk}:points=20",
            ),
        )
        self.assertFalse(CharacterGoal.objects.filter(character=self.ysmay.sheet_data).exists())
        self.assertIn(
            "25 points allocated across 2 domains.",
            self.telnet(
                self.ysmay,
                f"goal set domain={self.standing.pk}:points=20,domain={self.wealth.pk}:points=5",
            ),
        )
        self.assertEqual(
            sorted(
                CharacterGoal.objects.filter(character=self.ysmay.sheet_data).values_list(
                    "domain__name", "points"
                )
            ),
            [("Standing", 20), ("Wealth", 5)],
        )


class ClaimingRewards(JourneyCase):
    """Ysmay cashes in kudos, nominates Hobb, claims a random scene, picks a path and rests."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)

    def test_kudos_turn_into_xp(self) -> None:
        KudosPointsDataFactory(
            account=self.account_of(self.ysmay), total_earned=100, total_claimed=0
        )
        category = KudosClaimCategoryFactory(name="good_rp", kudos_cost=10, reward_amount=1)
        told = self.telnet(self.ysmay, "kudos")
        self.assertIn("Kudos available: 100", told)
        self.assertIn(f"[{category.pk}] Good Rp", told)
        self.assertIn("10 kudos", told)

        self.assertIn(
            "Claimed 50 kudos for 5 XP.", self.telnet(self.ysmay, f"kudos claim {category.pk} 50")
        )
        self.assertEqual(
            KudosPointsData.objects.get(account=self.account_of(self.ysmay)).total_claimed, 50
        )
        self.assertEqual(xp_of(self, self.ysmay), 5)
        # A claim too small to pay anything takes nothing, on the row or on the
        # balance she is shown next.
        self.assertIn(
            "Invalid amount for this conversion rate.",
            self.telnet(self.ysmay, f"kudos claim {category.pk} 5"),
        )
        self.assertIn("Kudos available: 50", self.telnet(self.ysmay, "kudos"))
        self.assertEqual(
            KudosPointsData.objects.get(account=self.account_of(self.ysmay)).total_claimed, 50
        )
        self.assertIn(
            "Insufficient kudos for this conversion.",
            self.telnet(self.ysmay, f"kudos claim {category.pk} 500"),
        )
        self.assertIn(
            "Invalid or inactive claim category.", self.telnet(self.ysmay, "kudos claim 99999 10")
        )
        self.assertIn(
            "Category id and amount must be numbers.",
            self.telnet(self.ysmay, f"kudos claim {category.pk} ten"),
        )
        self.assertIn(
            "Usage: kudos claim <category_id> <amount>", self.telnet(self.ysmay, "kudos claim")
        )
        self.assertIn("Kudos available: 50", self.telnet(self.ysmay, "kudos balance"))

    def test_a_pose_is_nominated_and_taken_back(self) -> None:
        get_current_game_week()
        self.telnet(self.ysmay, "scene start")
        self.telnet(self.hobb, "pose grins at the fire.")
        pose = Interaction.objects.get(persona=self.hobb.sheet_data.primary_persona)

        told = self.telnet(self.ysmay, "nominate")
        self.assertIn("Your nominations this week (they cannot see these):", told)
        self.assertIn("(none)", told)
        self.assertIn(
            "Nominated. They will not know who; it settles at week's end.",
            self.telnet(self.ysmay, f"nominate pose {pose.pk}"),
        )
        row = Nomination.objects.get(nominator=self.account_of(self.ysmay))
        self.assertEqual((row.nominee_id, row.target_id), (self.hobb.sheet_data.pk, pose.pk))
        self.assertNotTold(self.hobb, "Nominated")
        told = self.telnet(self.ysmay, "nominate list")
        self.assertIn("Hobb: ", told)
        self.assertIn(f"#{pose.pk}", told)
        self.assertIn(
            "You already nominated this piece this week.",
            self.telnet(self.ysmay, f"nominate pose {pose.pk}"),
        )
        self.assertIn(
            "You cannot nominate your own characters.",
            self.telnet(self.hobb, f"nominate pose {pose.pk}"),
        )

        # A journal entry counts only when it is public.
        self.telnet(self.ysmay, "journal write title=Private body=Mine alone.")
        private = JournalEntry.objects.get(author=self.ysmay.sheet_data)
        self.assertIn(
            "You can only nominate what you have seen.",
            self.telnet(self.hobb, f"nominate journal {private.pk}"),
        )
        self.assertIn(
            "Could not determine the author of this content.",
            self.telnet(self.hobb, "nominate journal 99999"),
        )

        self.assertIn(
            "Nomination withdrawn.", self.telnet(self.ysmay, f"nominate remove pose {pose.pk}")
        )
        self.assertFalse(Nomination.objects.exists())
        self.assertIn(
            "No nomination of yours on this piece this week.",
            self.telnet(self.ysmay, f"nominate remove pose {pose.pk}"),
        )
        self.assertIn(
            "Target type must be one of: pose, journal.",
            self.telnet(self.ysmay, "nominate banana 5"),
        )
        self.assertIn("Target id must be a number.", self.telnet(self.ysmay, "nominate pose x"))
        self.assertIn(
            "Usage: nominate [remove] <pose|journal> <id>", self.telnet(self.ysmay, "nominate pose")
        )

    def test_a_random_scene_is_claimed_and_another_rerolled(self) -> None:
        bram = self.make_player("Bram", room=self.lantern)
        self.make_player("Marrow", room=self.lantern)
        get_current_game_week()
        account = self.account_of(self.ysmay)
        target = RandomSceneTargetFactory(
            account=account,
            target_persona=self.hobb.sheet_data.primary_persona,
            slot_number=1,
            first_time=True,
        )
        self.assertIn(
            "You have no random-scene targets this week.", self.telnet(self.hobb, "randomscene")
        )
        self.assertIn(f"[{target.pk}] slot 1: Hobb (open)", self.telnet(self.ysmay, "randomscene"))
        self.assertIn(
            "No shared RP evidence found for this claim.",
            self.telnet(self.ysmay, f"randomscene claim {target.pk}"),
        )

        # A scene the two of them both pose in is the evidence.
        self.telnet(self.ysmay, "scene start")
        self.telnet(self.hobb, "pose nods.")
        self.telnet(self.ysmay, "pose nods back.")
        self.assertIn(
            "Claimed random scene with Hobb.", self.telnet(self.ysmay, f"rscene claim {target.pk}")
        )
        target.refresh_from_db()
        self.assertTrue(target.claimed)
        self.assertGreater(xp_of(self, self.ysmay), 0)
        self.assertGreater(xp_of(self, self.hobb), 0)
        self.assertIn(
            f"[{target.pk}] slot 1: Hobb (claimed)", self.telnet(self.ysmay, "randomscene")
        )
        self.assertIn(
            "This random scene target is already claimed.",
            self.telnet(self.ysmay, f"randomscene claim {target.pk}"),
        )
        self.assertIn(
            "Cannot reroll a claimed target.",
            self.telnet(self.ysmay, f"randomscene reroll {target.pk}"),
        )

        second = RandomSceneTargetFactory(
            account=account, target_persona=bram.sheet_data.primary_persona, slot_number=2
        )
        self.assertIn(
            "Rerolled to Marrow.", self.telnet(self.ysmay, f"randomscene reroll {second.pk}")
        )
        second.refresh_from_db()
        self.assertEqual(second.target_persona.name, "Marrow")
        self.assertTrue(second.rerolled)
        self.assertIn(
            "Already used reroll this week.",
            self.telnet(self.ysmay, f"randomscene reroll {second.pk}"),
        )
        self.assertIn(
            "Random scene target not found for this slot.",
            self.telnet(self.ysmay, "randomscene claim 99999"),
        )
        self.assertIn("Target id must be a number.", self.telnet(self.ysmay, "randomscene claim x"))
        self.assertIn(
            "Usage: randomscene [claim|reroll] <id>", self.telnet(self.ysmay, "randomscene frob 1")
        )

    def test_a_path_is_declared_and_she_rests(self) -> None:
        told = self.telnet(self.ysmay, "pathintent")
        self.assertIn("Current path: (none)", told)
        self.assertIn("(none available yet)", told)
        squire = PathFactory(name="Squire")
        champion = PathFactory(name="Champion")
        champion.parent_paths.add(squire)
        CharacterPathHistoryFactory(character=self.ysmay.sheet_data, path=squire)
        told = self.telnet(self.ysmay, "pathintent")
        self.assertIn("Current path: Squire", told)
        self.assertIn(f"[{champion.pk}] Champion", told)
        self.assertIn(
            "You intend to walk the path of Champion.",
            self.telnet(self.ysmay, f"pathintent {champion.pk}"),
        )
        self.assertEqual(
            PathIntent.objects.get(character_sheet=self.ysmay.sheet_data).intended_path_id,
            champion.pk,
        )
        self.assertIn("That is not a valid path.", self.telnet(self.ysmay, "pathintent 99999"))
        self.assertIn(
            "Usage: pathintent <path_id> | pathintent clear",
            self.telnet(self.ysmay, "pathintent abc"),
        )
        self.assertIn("Path intent cleared.", self.telnet(self.ysmay, "pathintent clear"))
        self.assertFalse(PathIntent.objects.filter(character_sheet=self.ysmay.sheet_data).exists())

        # Rest is for home, and it costs.
        self.assertIn("You can only rest at home.", self.telnet(self.ysmay, "rest"))
        self.ysmay.home = self.lantern
        self.ysmay.save()
        pool = ActionPointPool.get_or_create_for_character(self.ysmay)
        pool.current = 5
        pool.save()
        self.assertIn(
            "Not enough action points. Resting costs 10 AP.", self.telnet(self.ysmay, "rest")
        )
        pool.current = 50
        pool.save()
        self.assertIn(
            "You rest and feel refreshed. You will have increased stamina tomorrow.",
            self.telnet(self.ysmay, "rest"),
        )
        pool.refresh_from_db()
        self.assertEqual(pool.current, 40)
        self.assertTrue(get_or_create_fatigue_pool(self.ysmay.sheet_data).well_rested)
        self.assertIn("You have already rested today.", self.telnet(self.ysmay, "rest"))


class TrainingAndUnlocking(JourneyCase):
    """Ysmay plans her week's training and buys her next level with XP."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        ActionPointConfig.objects.update_or_create(
            name="Default", defaults={"is_active": True, "weekly_regen": 80}
        )
        self.skill = SkillFactory()
        self.specialization = SpecializationFactory(name="Swords")

    def test_training_is_planned_within_the_weekly_budget(self) -> None:
        told = self.telnet(self.ysmay, "training")
        self.assertIn("Weekly training budget: 0/80 AP used (80 left)", told)
        self.assertIn("No training allocations set.", told)

        mentor = self.hobb.sheet_data.primary_persona
        self.assertIn(
            f"Training allocation set for {self.skill.name}.",
            self.telnet(self.ysmay, f"training add skill={self.skill.pk} ap=20 mentor={mentor.pk}"),
        )
        self.assertIn(
            "Training allocation set for Swords.",
            self.telnet(self.ysmay, f"training add spec={self.specialization.pk} ap=15"),
        )
        skill_row = TrainingAllocation.objects.get(
            character=self.ysmay.sheet_data, skill=self.skill
        )
        spec_row = TrainingAllocation.objects.get(
            character=self.ysmay.sheet_data, specialization=self.specialization
        )
        self.assertEqual((skill_row.ap_amount, skill_row.mentor_id), (20, mentor.pk))
        told = self.telnet(self.ysmay, "training list")
        self.assertIn("35/80 AP used (45 left)", told)
        self.assertIn(f"[{skill_row.pk}] {self.skill.name}: 20 AP (mentor: Hobb)", told)
        self.assertIn(f"[{spec_row.pk}] Swords: 15 AP", told)

        self.assertIn(
            "Total allocated AP (85) would exceed weekly budget (80).",
            self.telnet(self.ysmay, f"training add skill={self.skill.pk} ap=50"),
        )
        self.assertIn(
            "Training allocation updated.",
            self.telnet(self.ysmay, f"training update id={skill_row.pk} ap=30 mentor="),
        )
        skill_row.refresh_from_db()
        self.assertEqual((skill_row.ap_amount, skill_row.mentor_id), (30, None))
        self.telnet(self.ysmay, f"training update id={skill_row.pk} mentor={mentor.pk}")
        skill_row.refresh_from_db()
        self.assertEqual(skill_row.mentor_id, mentor.pk)

        # Hobb's plan is his own.
        self.assertIn(
            "You can only update your own training allocations.",
            self.telnet(self.hobb, f"training update id={skill_row.pk} ap=5"),
        )
        self.assertIn(
            "You can only remove your own training allocations.",
            self.telnet(self.hobb, f"training remove id={skill_row.pk}"),
        )
        self.assertIn(
            "Training allocation removed.",
            self.telnet(self.ysmay, f"training remove id={spec_row.pk}"),
        )
        self.assertFalse(TrainingAllocation.objects.filter(pk=spec_row.pk).exists())
        self.assertIn(
            "No such training allocation.", self.telnet(self.ysmay, "training remove id=99999")
        )
        self.assertIn("No such skill.", self.telnet(self.ysmay, "training add skill=99999 ap=5"))
        self.assertIn(
            "No such mentor.",
            self.telnet(
                self.ysmay, f"training add spec={self.specialization.pk} ap=5 mentor=99999"
            ),
        )

        for line, reply in (
            ("training add ap=10", "Provide either skill=<id> or spec=<id>."),
            (
                "training add skill=1 spec=2 ap=10",
                "Provide either skill=<id> or spec=<id>, not both.",
            ),
            ("training add skill=1 ap=abc", "ap must be a positive integer."),
            ("training add skill=1 ap=0", "ap must be a positive integer."),
            ("training update ap=10", "id must be a positive integer."),
            ("training add skill=1 ap", "Expected key=value, got: ap"),
            (
                "training frobnicate",
                "Unknown training command 'frobnicate'. Try: add, list, remove, update.",
            ),
        ):
            self.assertIn(reply, self.telnet(self.ysmay, line), line)

    def test_a_class_level_is_unlocked_with_xp(self) -> None:
        warrior = CharacterClassFactory(name="Warrior")
        unlock = ClassLevelUnlock.objects.create(character_class=warrior, target_level=2)
        chart = XPCostChart.objects.create(name="Standard")
        XPCostEntry.objects.create(chart=chart, level=2, xp_cost=50)
        ClassXPCost.objects.create(character_class=warrior, cost_chart=chart)

        told = self.telnet(self.ysmay, "progression unlocks")
        self.assertIn("XP available: 0", told)
        self.assertIn("[class] Warrior level 2: 50 XP", told)
        self.assertNotIn("Recent XP transactions:", told)

        points = ExperiencePointsDataFactory(
            account=self.account_of(self.ysmay), total_earned=20, total_spent=0
        )
        self.assertIn(
            "Insufficient XP (need 50, have 20)",
            self.telnet(self.ysmay, f"progression unlock class={unlock.pk}"),
        )
        points.total_earned = 100
        points.save()
        self.assertIn(
            "Successfully unlocked Warrior Level 2",
            self.telnet(self.ysmay, f"progression unlock class={unlock.pk}"),
        )
        receipt = CharacterUnlock.objects.get(character=self.ysmay.sheet_data)
        self.assertEqual(
            (receipt.character_class_id, receipt.target_level, receipt.xp_spent),
            (warrior.pk, 2, 50),
        )
        self.assertEqual(xp_of(self, self.ysmay), 50)
        told = self.telnet(self.ysmay, "progression")
        self.assertIn("XP available: 50", told)
        self.assertIn("Recent XP transactions:", told)
        self.assertIn("-50 XP", told)
        self.assertIn("No class-level unlocks available.", told)
        self.assertIn(
            "Already unlocked", self.telnet(self.ysmay, f"progression unlock class={unlock.pk}")
        )

        self.assertIn(
            "No such class-level unlock.", self.telnet(self.ysmay, "progression unlock class=99999")
        )
        self.assertIn(
            f"{self.skill.name} has no recorded value for this character.",
            self.telnet(self.ysmay, f"progression unlock skill={self.skill.pk}"),
        )
        oldtongue = LanguageFactory(name="Oldtongue")
        self.assertIn(
            "Your Oldtongue is not waiting at a breakthrough.",
            self.telnet(self.ysmay, f"progression unlock language={oldtongue.pk}"),
        )
        self.assertIn(
            "No such language.", self.telnet(self.ysmay, "progression unlock language=99999")
        )
        self.assertIn(
            "No such thread.", self.telnet(self.ysmay, "progression unlock thread=99999 level=10")
        )
        for line, reply in (
            ("progression unlock thread=2", "level must be a positive integer."),
            (
                "progression unlock",
                "Provide class=<id>, thread=<id> level=<n>, skill=<id>, or language=<id>.",
            ),
            (
                "progression unlock class=1 thread=2 level=10",
                "Provide exactly one of class=<id>, thread=<id>, skill=<id>, or language=<id>.",
            ),
            ("progression unlock class=abc", "class must be a positive integer."),
            ("progression frobnicate", "Unknown progression command."),
        ):
            self.assertIn(reply, self.telnet(self.ysmay, line), line)

        stray = CharacterFactory(db_key="Stray", location=self.lantern)
        CharacterSheetFactory(character=stray)
        self.assertIn(
            "XP available: 0 (no active character on the roster)",
            self.telnet(stray, "progression unlocks"),
        )


class LearningAGift(JourneyCase):
    """Ysmay buys a gift's unlock, takes up Hobb's teaching and looks at her meters."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        self.sight = GiftFactory(name="Sight", kind=GiftKind.MINOR)
        # The gift's supported resonance is what its thread is woven with on the
        # first technique; a character with no claimed resonance has nothing else.
        self.sight.resonances.add(ResonanceFactory(name="Clarity"))
        self.unlock = GiftUnlockFactory(gift=self.sight, xp_cost=25)
        self.soulsight = TechniqueFactory(gift=self.sight, name="Soulsight")
        self.offer = TechniqueTeachingOfferFactory(
            teacher=tenure_of(self.hobb),
            technique=self.soulsight,
            pitch="Learn to see souls",
            learn_ap_cost=5,
            banked_ap=0,
        )
        self.weaving = ThreadWeavingTeachingOfferFactory(
            teacher=tenure_of(self.hobb), pitch="Learn to weave"
        )

    def test_a_gift_is_unlocked_and_a_technique_taken_up(self) -> None:
        told = strip_ansi(self.telnet(self.ysmay, "learn"))
        self.assertIn("Learn actions: gift <id>, technique <id>, thread <id>", told)
        self.assertIn(f"[gift {self.unlock.pk}] Sight: 25 XP (not purchased)", told)
        self.assertIn(f"[technique {self.offer.pk}] Soulsight", told)
        self.assertIn(
            f"5 AP, taught by {tenure_of(self.hobb).display_name}: Learn to see souls", told
        )
        self.assertIn(f"[thread {self.weaving.pk}]", told)
        self.assertIn("Learn to weave", told)

        self.assertIn(
            "You must unlock this gift before learning its techniques.",
            self.telnet(self.ysmay, f"learn technique {self.offer.pk}"),
        )
        points = ExperiencePointsDataFactory(
            account=self.account_of(self.ysmay), total_earned=0, total_spent=0
        )
        self.assertIn(
            "You do not have enough XP for this.",
            self.telnet(self.ysmay, f"learn gift {self.unlock.pk}"),
        )
        points.total_earned = 30
        points.save()
        self.assertIn(
            "Unlocked Sight for 25 XP.", self.telnet(self.ysmay, f"learn gift {self.unlock.pk}")
        )
        self.assertTrue(
            CharacterGiftUnlock.objects.filter(
                character=self.ysmay.sheet_data, unlock=self.unlock
            ).exists()
        )
        self.assertEqual(xp_of(self, self.ysmay), 5)
        self.assertIn(
            f"[gift {self.unlock.pk}] Sight: 25 XP (purchased)",
            self.telnet(self.ysmay, "learn status"),
        )

        self.assertIn(
            "You learn Soulsight.", self.telnet(self.ysmay, f"learn technique {self.offer.pk}")
        )
        meter = TechniqueProgress.objects.get(
            character_sheet=self.ysmay.sheet_data, technique=self.soulsight
        )
        self.assertEqual(meter.points_accumulated, 0)
        self.assertEqual(meter.teacher_tenure_id, tenure_of(self.hobb).pk)
        self.assertTrue(
            CharacterGift.objects.filter(character=self.ysmay.sheet_data, gift=self.sight).exists()
        )
        self.assertIn(
            "You do not have enough XP for this.",
            self.telnet(self.ysmay, f"learn thread {self.weaving.pk}"),
        )

        # The meter is hers to look at and to train against.
        told = self.telnet(self.ysmay, "train")
        self.assertIn("Your in-progress technique meters:", told)
        self.assertIn(
            f"Soulsight: 0/{meter.total_required} (teacher: {tenure_of(self.hobb).display_name})",
            told,
        )
        self.assertIn("You aren't training any techniques.", self.telnet(self.hobb, "train"))
        self.assertIn(
            "You must invest a positive amount of AP.", self.telnet(self.ysmay, "train soulsight=0")
        )
        self.assertIn(
            "Technique training is not configured on this server yet.",
            self.telnet(self.ysmay, "train Soulsight=2"),
        )
        ember = TechniqueFactory(name="Ember Lance")
        self.assertIn(
            "You aren't training that technique. Accept a teaching offer or an Academy TRAIN "
            "offer to start a meter first.",
            self.telnet(self.ysmay, f"train {ember.name.lower()}"),
        )
        self.assertIn(
            "'abc' is not a valid AP amount.", self.telnet(self.ysmay, "train Soulsight=abc")
        )
        self.assertIn("Usage: train <technique>[=<ap>].", self.telnet(self.ysmay, "train =20"))
        self.assertIn(
            "There is no technique called 'Nothing'.", self.telnet(self.ysmay, "train Nothing")
        )

        self.assertIn("Unknown gift_unlock_id.", self.telnet(self.ysmay, "learn gift 99999"))
        self.assertIn("Unknown offer_id.", self.telnet(self.ysmay, "learn technique 99999"))
        self.assertIn("Unknown offer_id.", self.telnet(self.ysmay, "learn thread 99999"))
        self.assertIn("Usage: learn gift <id>.", self.telnet(self.ysmay, "learn gift"))
        self.assertIn(
            "Usage: learn technique <id>.", self.telnet(self.ysmay, "learn technique abc")
        )
        self.assertIn(
            "Unknown learn action 'frobnicate'. Try: gift, technique, thread.",
            self.telnet(self.ysmay, "learn frobnicate 1"),
        )


class CatchingUpOnTidings(JourneyCase):
    """Ysmay hears what her circles are saying, and what the square's board carries."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.compact = SocietyFactory(name="The Compact")
        SocietyReputationFactory(
            persona=self.ysmay.sheet_data.primary_persona, society=self.compact, value=300
        )

    def test_her_circles_tell_her_the_news(self) -> None:
        self.assertIn(
            "There are no tidings circulating in your circles right now.",
            self.telnet(self.ysmay, "tidings"),
        )
        deed = LegendEntryFactory(title="slew the wyrm")
        deed.societies_aware.add(self.compact)
        scandal = SecretFactory(content="consorts with the abyss")
        scandal.societies_exposed.add(self.compact)
        told = strip_ansi(self.telnet(self.ysmay, "tidings"))
        self.assertIn("The tidings of your circles:", told)
        self.assertIn("slew the wyrm", told)
        self.assertIn("consorts with the abyss", told)
        self.assertIn(
            "Usage: tidings  or  tidings local", self.telnet(self.ysmay, "tidings gossip")
        )
        self.assertIn(
            "There is no notice board or crier here; local tidings are found where folk gather.",
            self.telnet(self.ysmay, "tidings local"),
        )

        # The feed follows the face she wears: a mask belongs to no society, and an
        # established face has circles of its own.
        self.telnet(self.ysmay, "persona mask The Veil")
        self.assertIn(
            "There are no tidings circulating in your circles right now.",
            self.telnet(self.ysmay, "tidings"),
        )
        self.telnet(self.ysmay, "persona create The Grey Lady")
        grey_lady = Persona.objects.get(character_sheet=self.ysmay.sheet_data, name="The Grey Lady")
        hollow = SocietyFactory(name="The Hollow")
        SocietyReputationFactory(persona=grey_lady, society=hollow, value=200)
        other_deed = LegendEntryFactory(title="deed of her other face")
        other_deed.societies_aware.add(hollow)
        self.telnet(self.ysmay, "persona The Grey Lady")
        told = self.telnet(self.ysmay, "tidings")
        self.assertIn("deed of her other face", told)
        self.assertNotIn("slew the wyrm", told)
        self.telnet(self.ysmay, "persona Ysmay")
        self.assertIn("slew the wyrm", self.telnet(self.ysmay, "tidings"))

        stray = CharacterFactory(db_key="Stray", location=self.lantern)
        CharacterSheetFactory(character=stray)
        self.assertIn(
            "You have no active character to catch up on the tidings with.",
            self.telnet(stray, "tidings"),
        )

    @override_settings(SEED_SAMPLE_CONTENT=True)
    def test_the_square_has_a_board_or_a_crier(self) -> None:
        crown = SocietyFactory(name="The Crown")
        kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=crown)
        square = self.make_room("The Square")
        profile = RoomProfileFactory(objectdb=square, area=kingdom)
        self.ysmay.location = square
        self.ysmay.save()
        self.assertIn(
            "There is no notice board or crier here", self.telnet(self.ysmay, "tidings local")
        )

        board = RoomFeatureInstance.objects.create(
            room_profile=profile, feature_kind=ensure_notice_board_kind()
        )
        self.assertIn(
            "The local tidings are quiet; nothing worth repeating today.",
            self.telnet(self.ysmay, "tidings local"),
        )
        deed = LegendEntryFactory(title="crowned the tourney")
        deed.societies_aware.add(crown)
        told = strip_ansi(self.telnet(self.ysmay, "tidings local"))
        self.assertIn("Pinned to the notice board:", told)
        self.assertIn("crowned the tourney", told)

        board.feature_kind = ensure_town_crier_kind()
        board.save()
        told = strip_ansi(self.telnet(self.ysmay, "tidings local"))
        self.assertIn("The crier calls out the news of the day:", told)
        self.assertIn("crowned the tourney", told)


class MindingTheAccount(JourneyCase):
    """Ysmay's player reads the account, sets its email and checks their applications."""

    def setUp(self) -> None:
        super().setUp()
        self.lantern = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.lantern)
        self.account = self.account_of(self.ysmay)
        self.watch(self.account)

    def typed(self, line: str) -> str:
        """Type ``line`` as Ysmay's puppet; the account's commands answer the
        account, which on a telnet session is the same screen."""
        box = self.mailbox(self.account)
        start = len(box.lines)
        told = self.telnet(self.ysmay, line)
        return "\n".join([told, *box.lines[start:]])

    def test_the_account_is_read_and_an_email_set(self) -> None:
        told = self.typed("account")
        self.assertIn(f"Account Information for {self.account.username}", told)
        self.assertIn("Character Access: 1 character(s)", told)
        self.assertIn("  Ysmay", told)
        self.assertIn(
            "Unknown account command 'frobnicate'. Try: email <address>.",
            self.typed("account frobnicate"),
        )
        self.assertIn(
            "'not-an-email' doesn't look like a valid email address.",
            self.typed("account email not-an-email"),
        )
        self.assertFalse(EmailAddress.objects.filter(user=self.account).exists())

        told = self.typed("account email NewPlayer@example.com")
        self.assertIn(
            "Account email set to newplayer@example.com. A verification link has been sent", told
        )
        address = EmailAddress.objects.get(user=self.account, email="newplayer@example.com")
        self.assertTrue(address.primary)
        self.assertFalse(address.verified)
        self.assertEqual([message.to for message in mail.outbox], [["newplayer@example.com"]])
        self.assertFalse(self.account.player_data.can_apply_for_characters())

        address.verified = True
        address.save(update_fields=["verified"])
        self.assertTrue(self.account.player_data.can_apply_for_characters())
        self.assertIn(
            "Your account email is already set and verified: newplayer@example.com",
            self.typed("account email newplayer@example.com"),
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_her_applications_are_listed(self) -> None:
        self.assertIn("You have no pending roster applications.", self.typed("roster"))
        hopeful = CharacterSheetFactory(character__db_key="Hopeful")
        RosterApplicationFactory(
            player_data=self.account.player_data,
            character=hopeful,
            status=ApplicationStatus.PENDING,
        )
        RosterApplicationFactory(
            player_data=self.account.player_data,
            character=CharacterSheetFactory(character__db_key="AlreadyIn"),
            status=ApplicationStatus.APPROVED,
        )
        hobb = self.make_player("Hobb", room=self.lantern)
        RosterApplicationFactory(
            player_data=self.account_of(hobb).player_data,
            character=CharacterSheetFactory(character__db_key="NotYours"),
            status=ApplicationStatus.PENDING,
        )
        told = self.typed("roster status")
        self.assertIn("Your pending roster applications:", told)
        self.assertIn("Hopeful", told)
        self.assertIn("Pending Review", told)
        self.assertNotIn("AlreadyIn", told)
        self.assertNotIn("NotYours", told)
        self.assertIn(
            "Unknown roster command 'browse'. Try: roster status.", self.typed("roster browse")
        )
