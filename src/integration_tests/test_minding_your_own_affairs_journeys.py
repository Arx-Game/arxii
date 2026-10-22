"""Journeys for the commands ledger (#3657, tranche 18): minding your own affairs. A
character manufactures a scandal against someone who let her, and names a crime; tells
the tale of a deed and another writes down what he heard; sets the terms on which others
may act on her; searches a room and opens an investigation from the lead it turns up;
opens and closes a window in the room she keeps; gathers what her own crime left behind
and disposes of it (tranche 21). Each types what the person types through the real
command handler and asserts what they were told and what the rows now hold."""

from __future__ import annotations

from django.test import override_settings

from actions.constants import ActionBackend
from actions.player_interface import dispatch_player_action
from actions.types import ActionRef
from commands import pending_actions
from evennia_extensions.constants import ExitKind
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from evennia_extensions.models import ExitProfile
from integration_tests.harness import JourneyCase
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.constants import ClueResolution
from world.clues.factories import ClueFactory, RoomClueFactory
from world.clues.models import CharacterClue
from world.consent.constants import ConsentMode
from world.consent.factories import SocialConsentCategoryFactory
from world.consent.models import (
    SocialConsentBlacklist,
    SocialConsentCategoryRule,
    SocialConsentWhitelist,
)
from world.items.models import ItemInstance
from world.justice.constants import EvidenceState
from world.justice.factories import CrimeKindFactory
from world.justice.models import AccusationCrimeClaim, CrimeEvidence
from world.justice.services import tag_deed_crimes
from world.locations.constants import LocationRole
from world.locations.factories import LocationTenancyFactory
from world.projects.constants import ProjectKind, ProjectStatus
from world.projects.models import Project
from world.room_features.factories import RoomFeatureInstanceFactory
from world.room_features.seeds import ensure_lab_kind
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction
from world.secrets.constants import SecretProvenance
from world.secrets.models import Secret
from world.secrets.services import grant_secret_knowledge
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.investigation_checks import seed_investigation_check_content
from world.seeds.security_checks import seed_security_check_content
from world.societies.factories import LegendEntryFactory
from world.societies.models import LegendDeedStory, LegendSpread, PersonaDeedKnowledge
from world.traits.factories import CheckOutcomeFactory


def persona_of(character):
    return character.sheet_data.primary_persona


def tenure_of(character):
    return character.sheet_data.roster_entry.tenures.get(end_date__isnull=True)


def fill_action_points(character) -> None:
    pool = ActionPointPool.get_or_create_for_character(character)
    pool.current = 200
    pool.save()


class ManufacturingAScandal(JourneyCase):
    """Ysmay has it in for Hobb. Whether she may frame him is his consent to give, a
    named crime draws the law's eye, and the scandal is his to dispute."""

    def setUp(self) -> None:
        super().setUp()
        self.tavern = self.make_room("The Gilded Cup")
        self.ysmay = self.make_player("Ysmay", room=self.tavern)
        self.hobb = self.make_player("Hobb", room=self.tavern)
        # Antagonism is opt-in: the seeded category admits friends and the whitelist only.
        SocialConsentCategoryFactory(
            key="hostile", name="Hostile", default_mode=ConsentMode.FRIENDS_WHITELIST
        )
        CrimeKindFactory(slug="theft", name="Theft")

    def test_a_scandal_and_then_a_crime(self) -> None:
        usage = "Usage: accuse <character> = <the claim>"
        self.assertIn(usage, self.telnet(self.ysmay, "accuse"))
        self.assertIn(usage, self.telnet(self.ysmay, "accuse Hobb ="))
        self.assertIn(usage, self.telnet(self.ysmay, "accuse = he waters the wine"))
        self.assertIn(
            "Could not find 'Nobody'.",
            self.telnet(self.ysmay, "accuse Nobody = he waters the wine"),
        )

        told = self.telnet(self.ysmay, "accuse Hobb = he waters the wine")
        self.assertIn(
            "Hobb has not opened themselves to being antagonised. You can't manufacture a "
            "scandal against them.",
            told,
        )
        self.assertFalse(Secret.objects.filter(subject_sheet=self.hobb.sheet_data).exists())

        self.assertIn(
            "Hostile set to everyone.", self.telnet(self.hobb, "consent category hostile=everyone")
        )
        told = self.telnet(self.ysmay, "accuse Hobb = he waters the wine")
        self.assertIn("You mint a scandal against Hobb. Now to make it stick.", told)
        scandal = Secret.objects.get(subject_sheet=self.hobb.sheet_data)
        self.assertEqual(scandal.provenance, SecretProvenance.ACCUSATION)
        self.assertEqual(scandal.content, "he waters the wine")

        crime_usage = "Usage: accuse/crime <character> = <crime-kind> : <the claim>"
        self.assertIn(crime_usage, self.telnet(self.ysmay, "accuse/crime Hobb = he stole it"))
        self.assertIn(crime_usage, self.telnet(self.ysmay, "accuse/crime Hobb = theft :"))
        self.assertIn(crime_usage, self.telnet(self.ysmay, "accuse/crime = theft : he stole it"))
        self.assertIn(
            "There's no such crime to accuse them of: 'arson'.",
            self.telnet(self.ysmay, "accuse/crime Hobb = arson : he burned the mill"),
        )
        told = self.telnet(self.ysmay, "accuse/crime Hobb = theft : he stole the chalice")
        self.assertIn(
            "You accuse Hobb of Theft. Where that's a crime, the law will start to look their "
            "way, until someone disproves it.",
            told,
        )
        claim = AccusationCrimeClaim.objects.get(secret__content="he stole the chalice")
        self.assertEqual(claim.crime_kind.slug, "theft")
        self.assertEqual(claim.secret.subject_sheet_id, self.hobb.sheet_data.pk)

    def test_the_scandal_is_his_to_dispute(self) -> None:
        self.assertIn(
            "You hold no manufactured scandals worth disputing.",
            self.telnet(self.hobb, "accuse/refute"),
        )
        self.assertIn("Usage: accuse/refute [<#>]", self.telnet(self.hobb, "accuse/refute first"))
        self.assertIn("No scandal #3.", self.telnet(self.hobb, "accuse/refute 3"))
        self.assertIn(
            "You hold no proven fabrications to lay at anyone's feet.",
            self.telnet(self.hobb, "accuse/denounce"),
        )
        self.assertIn("Usage: accuse/denounce [<#>]", self.telnet(self.hobb, "accuse/denounce x"))
        self.assertIn("No fabrication #2.", self.telnet(self.hobb, "accuse/denounce 2"))

        self.telnet(self.hobb, "consent category hostile=everyone")
        self.telnet(self.ysmay, "accuse Hobb = he waters the wine")
        scandal = Secret.objects.get(subject_sheet=self.hobb.sheet_data)
        grant_secret_knowledge(roster_entry=self.hobb.sheet_data.roster_entry, secret=scandal)

        told = self.telnet(self.hobb, "accuse/refute")
        self.assertIn("Scandals you could refute:", told)
        self.assertIn("  1. he waters the wine", told)
        # The Gilded Cup is no social hub, so the defense cannot be made here.
        self.assertIn(
            "You can only work the rumor mill at a social hub.",
            self.telnet(self.hobb, "accuse/refute 1"),
        )


class SpreadingATale(JourneyCase):
    """Ysmay sank the Argent. She tells the tale in the Long Hall's scene; Hobb, who had
    never heard of it, writes down what he heard."""

    def setUp(self) -> None:
        super().setUp()
        self.hall = self.make_room("The Long Hall")
        self.ysmay = self.make_player("Ysmay", room=self.hall)
        self.hobb = self.make_player("Hobb", room=self.hall)
        self.scene = SceneFactory(
            room=self.hall,
            participants=[self.account_of(self.ysmay), self.account_of(self.hobb)],
        )
        self.deed = LegendEntryFactory(
            persona=persona_of(self.ysmay), title="The Sinking of the Argent", base_value=50
        )
        fill_action_points(self.ysmay)
        fill_action_points(self.hobb)
        self.watch(self.hobb)

    def test_a_tale_told_and_written_down(self) -> None:
        usage = "Usage: deed spread <deed> [...] | deed story <deed>=<text>"
        self.assertIn(usage, self.telnet(self.ysmay, "deed"))
        self.assertIn(usage, self.telnet(self.ysmay, "deed dance"))
        self.assertIn(
            "Spread what deed? (deed spread <deed name or id>)",
            self.telnet(self.ysmay, "deed spread"),
        )
        self.assertIn(
            "You don't know a deed matching 'The Fall of Nowhere'.",
            self.telnet(self.ysmay, "deed spread The Fall of Nowhere"),
        )
        self.assertIn(
            "Effort must be low, medium, or high.",
            self.telnet(self.ysmay, "deed spread The Sinking of the Argent effort=heroic"),
        )
        self.assertIn(
            "No usable specialization matching 'Juggling'.",
            self.telnet(self.ysmay, "deed spread The Sinking of the Argent spec=Juggling"),
        )
        self.assertIn(
            "You don't know a deed matching 'The Sinking of the Argent'.",
            self.telnet(self.hobb, "deed story The Sinking of the Argent=I heard it sung."),
        )

        # The web's spread names the persona, the scene and the deed by id, and the action
        # answers each thing that is not hers to tell.
        spread = ActionRef(backend=ActionBackend.SCENE_ADAPTIVE, registry_key="spread_tale")
        mine = persona_of(self.ysmay).pk

        def sent(**kwargs):
            return dispatch_player_action(self.ysmay, spread, kwargs).detail.message

        self.assertEqual(
            sent(scene_id=self.scene.pk, deed_id=self.deed.pk), "You must choose a persona."
        )
        self.assertEqual(
            sent(persona_id=persona_of(self.hobb).pk, scene_id=self.scene.pk, deed_id=self.deed.pk),
            "You do not control that persona.",
        )
        self.assertEqual(sent(persona_id=mine, deed_id=self.deed.pk), "You must be in a scene.")
        self.assertEqual(
            sent(persona_id=mine, scene_id=self.scene.pk), "You must choose a deed to spread."
        )
        his = LegendEntryFactory(persona=persona_of(self.hobb), title="The Sack of Hob's Mill")
        self.assertEqual(
            sent(persona_id=mine, scene_id=self.scene.pk, deed_id=his.pk),
            "This persona is not aware of that deed.",
        )
        self.assertEqual(
            sent(
                persona_id=mine,
                scene_id=self.scene.pk,
                deed_id=self.deed.pk,
                specialization_id=999999,
            ),
            "That form cannot be used to spread a tale.",
        )
        self.assertFalse(LegendSpread.objects.exists())

        with force_check_outcome(CheckOutcomeFactory(name="Told well", success_level=2)) as roll:
            told = self.telnet(
                self.ysmay,
                "deed spread The Sinking of the Argent effort=high specialization=Singing "
                "pose=She sings of the Argent going down.",
            )
        self.assertEqual(roll.check_type.name, "Spread a Tale")
        self.assertIn("You spread the tale of The Sinking of the Argent.", told)
        spread = LegendSpread.objects.get(legend_entry=self.deed)
        self.assertGreater(spread.value_added, 0)
        self.assertEqual(spread.spreader_persona_id, persona_of(self.ysmay).pk)
        # The telling is the scene's record; a journey character has no session for the push.
        self.assertTrue(
            Interaction.objects.filter(
                scene=self.scene, content__icontains="Argent going down"
            ).exists()
        )
        self.assertTrue(
            PersonaDeedKnowledge.objects.filter(
                deed=self.deed, persona=persona_of(self.hobb)
            ).exists()
        )
        # A second telling straight after the first waits out the scene's cooldown.
        self.assertIn(
            "You must wait before acting again.",
            self.telnet(self.ysmay, f"deed spread {self.deed.pk}"),
        )

        self.assertIn(
            "Record a story how? (deed story <deed name or id>=<written account>)",
            self.telnet(self.hobb, "deed story The Sinking of the Argent"),
        )
        self.assertIn(
            "Record a story about which deed?",
            self.telnet(self.hobb, "deed story =I heard it sung."),
        )
        self.assertIn(
            "You must write something.",
            self.telnet(self.hobb, "deed story The Sinking of the Argent="),
        )
        told = self.telnet(
            self.hobb, "deed story The Sinking of the Argent=I heard it sung in the Long Hall."
        )
        self.assertIn("You record your account of the deed.", told)
        story = LegendDeedStory.objects.get(deed=self.deed, author=persona_of(self.hobb))
        self.assertEqual(story.text, "I heard it sung in the Long Hall.")

        # The web's story is the same action, by the deed's id; the cooldown has passed.
        pending_actions._LAST_ACTED.pop(self.hobb.sheet_data.pk, None)
        result = dispatch_player_action(
            self.hobb,
            ActionRef(backend=ActionBackend.SCENE_ADAPTIVE, registry_key="save_deed_story"),
            {"persona_id": persona_of(self.hobb).pk, "deed_id": self.deed.pk, "text": "Rewritten."},
        )
        self.assertTrue(result.detail.success, result.detail.message)
        story.refresh_from_db()
        self.assertEqual(story.text, "Rewritten.")

    def test_a_tale_needs_a_scene_she_is_part_of(self) -> None:
        yard = self.make_room("The Yard")
        orla = self.make_player("Orla", room=yard)
        theirs = SceneFactory(room=yard, participants=[self.account_of(orla)])
        quiet = self.make_room("The Back Stair")
        self.ysmay.move_to(quiet, quiet=True)
        self.assertIn(
            "There is no active scene here.",
            self.telnet(self.ysmay, "deed spread The Sinking of the Argent"),
        )
        self.ysmay.move_to(yard, quiet=True)
        self.assertIn(
            "You are not a participant in this scene.",
            self.telnet(self.ysmay, "deed spread The Sinking of the Argent"),
        )
        # The web names the scene by id, and the action refuses one she is no part of.
        result = dispatch_player_action(
            self.ysmay,
            ActionRef(backend=ActionBackend.SCENE_ADAPTIVE, registry_key="spread_tale"),
            {
                "persona_id": persona_of(self.ysmay).pk,
                "scene_id": theirs.pk,
                "deed_id": self.deed.pk,
            },
        )
        self.assertEqual(result.detail.message, "You are not a participant in that scene.")
        self.assertFalse(LegendSpread.objects.exists())


class SettingHerTerms(JourneyCase):
    """Ysmay reads her consent settings, learns what the modes mean, sets a category and
    keeps her lists. The categories' effect on a carry is the body-handling journey's."""

    def setUp(self) -> None:
        super().setUp()
        self.parlor = self.make_room("The Parlor")
        self.ysmay = self.make_player("Ysmay", room=self.parlor)
        self.hobb = self.make_player("Hobb", room=self.parlor)
        self.romantic = SocialConsentCategoryFactory(key="romantic", name="Romantic")
        self.menace = SocialConsentCategoryFactory(key="menace", name="Menace")

    def test_reading_the_terms_and_the_usages(self) -> None:
        told = self.telnet(self.ysmay, "consent")
        self.assertIn("Consent settings:", told)
        self.assertIn("  Social actions: allowed", told)
        self.assertIn(
            "  No per-category rules set (all categories use the global preference).", told
        )
        self.assertIn("  No whitelist entries.", told)
        self.assertIn("  No blacklist entries.", told)

        told = self.telnet(self.ysmay, "consent modes")
        self.assertIn("Consent modes", told)
        for mode in ConsentMode:
            self.assertIn(mode.label, told)

        usage = "consent whitelist add <name> to <category>"
        self.assertIn(usage, self.telnet(self.ysmay, "consent nonsense"))
        self.assertIn(usage, self.telnet(self.ysmay, "consent category romantic"))
        self.assertIn(usage, self.telnet(self.ysmay, "consent whitelist"))
        self.assertIn(usage, self.telnet(self.ysmay, "consent blacklist frobnicate Hobb"))
        self.assertIn(
            "Usage: consent whitelist add <name> to <category>.",
            self.telnet(self.ysmay, "consent whitelist add Hobb"),
        )
        self.assertIn(
            "Usage: consent blacklist remove <name> from <category>.",
            self.telnet(self.ysmay, "consent blacklist remove Hobb"),
        )
        self.assertIn(
            "Could not find 'Nobody'.",
            self.telnet(self.ysmay, "consent whitelist add Nobody to romantic"),
        )
        cleo = CharacterFactory(db_key="Cleo", location=self.parlor)
        CharacterSheetFactory(character=cleo)
        self.assertIn(
            "Cleo has no active character tenure.",
            self.telnet(self.ysmay, "consent whitelist add Cleo to romantic"),
        )
        self.assertIn("You have no active character tenure.", self.telnet(cleo, "consent on"))
        shade = CharacterFactory(db_key="Shade", location=self.parlor)
        self.assertIn("You have no character identity.", self.telnet(shade, "consent"))
        self.assertFalse(SocialConsentWhitelist.objects.exists())

    def test_a_rule_and_the_lists(self) -> None:
        self.assertIn(
            "Romantic set to whitelist.",
            self.telnet(self.ysmay, "consent category romantic=whitelist"),
        )
        rule = SocialConsentCategoryRule.objects.get(
            preference__tenure=tenure_of(self.ysmay), category=self.romantic
        )
        self.assertEqual(rule.mode, ConsentMode.ALLOWLIST)
        self.assertIn("    Romantic: whitelist", self.telnet(self.ysmay, "consent"))

        self.telnet(self.ysmay, "consent whitelist add Hobb to romantic")
        self.telnet(self.ysmay, "consent blacklist add Hobb to menace")
        self.assertTrue(
            SocialConsentWhitelist.objects.filter(
                owner_tenure=tenure_of(self.ysmay),
                allowed_tenure=tenure_of(self.hobb),
                category=self.romantic,
            ).exists()
        )
        self.assertTrue(
            SocialConsentBlacklist.objects.filter(
                owner_tenure=tenure_of(self.ysmay),
                blocked_tenure=tenure_of(self.hobb),
                category=self.menace,
            ).exists()
        )

        told = self.telnet(self.ysmay, "consent whitelist list")
        self.assertIn("Whitelist entries:", told)
        self.assertIn("Blacklist entries:", told)
        self.assertIn("Hobb", told)
        self.assertIn(" - Romantic", told)
        self.assertIn(" - Menace", told)
        told = self.telnet(self.ysmay, "consent blacklist list romantic")
        self.assertIn("Whitelist for Romantic:", told)
        self.assertIn("  No blacklist entries for Romantic.", told)
        self.assertNotIn("Menace", told)
        self.assertIn(
            "  No category named 'hugging'.",
            self.telnet(self.ysmay, "consent whitelist list hugging"),
        )

        self.assertIn(
            "Romantic reverted to default (everyone).",
            self.telnet(self.ysmay, "consent category romantic=default"),
        )
        self.assertFalse(SocialConsentCategoryRule.objects.filter(category=self.romantic).exists())

        self.assertIn("Social actions are now blocked.", self.telnet(self.ysmay, "consent off"))
        self.assertIn("  Social actions: blocked", self.telnet(self.ysmay, "consent"))
        self.assertIn("Social actions are now allowed.", self.telnet(self.ysmay, "consent on"))


@override_settings(SEED_SAMPLE_CONTENT=True)
class SearchingTheRoom(JourneyCase):
    """Ysmay searches the study, finds a ledger that wants researching, and opens the
    investigation once she has a lab to run it from. The Search check is sample content."""

    def setUp(self) -> None:
        super().setUp()
        seed_investigation_check_content()
        self.study = self.make_room("The Study")
        self.profile = RoomProfileFactory(objectdb=self.study)
        self.ysmay = self.make_player("Ysmay", room=self.study)
        fill_action_points(self.ysmay)
        self.clue = ClueFactory(
            name="A ledger in a false drawer",
            description="Accounts kept in two hands.",
            resolution_mode=ClueResolution.RESEARCH,
        )
        RoomClueFactory(room_profile=self.profile, clue=self.clue, detect_difficulty=10)
        self.lab = ensure_lab_kind()

    def held(self) -> bool:
        return CharacterClue.objects.filter(
            roster_entry=self.ysmay.sheet_data.roster_entry, clue=self.clue
        ).exists()

    def test_a_search_and_the_lead_it_turns_up(self) -> None:
        with force_check_outcome(CheckOutcomeFactory(name="Missed", success_level=-1)) as roll:
            told = self.telnet(self.ysmay, "search")
        self.assertEqual(roll.check_type.name, "Search")
        self.assertEqual(roll.target_difficulty, 10)
        self.assertIn("You search but turn up nothing.", told)
        self.assertFalse(self.held())
        self.assertIn(
            "You hold no leads that want researching.", self.telnet(self.ysmay, "search start")
        )

        with force_check_outcome(CheckOutcomeFactory(name="Found", success_level=1)):
            told = self.telnet(self.ysmay, "investigate")
        self.assertIn("You uncover something:", told)
        self.assertIn("  A ledger in a false drawer - Accounts kept in two hands.", told)
        self.assertTrue(self.held())
        # Held already: there is nothing left in the study to find, by telnet or the web.
        self.assertIn("You search but turn up nothing.", self.telnet(self.ysmay, "search"))
        self.assertIn(
            "You search but turn up nothing.", self.web(self.ysmay, "search").detail.message
        )

        told = self.telnet(self.ysmay, "search start")
        self.assertIn("Leads you could research:", told)
        self.assertIn("  1. A ledger in a false drawer", told)
        self.assertIn("Usage: search start [<#>]", self.telnet(self.ysmay, "search start first"))
        self.assertIn("No lead #4.", self.telnet(self.ysmay, "search start 4"))
        self.assertIn(
            "You need a research lab to run an investigation from.",
            self.telnet(self.ysmay, "search start 1"),
        )

        RoomFeatureInstanceFactory(room_profile=self.profile, feature_kind=self.lab)
        told = self.telnet(self.ysmay, "search start 1")
        self.assertIn("You open an investigation: A ledger in a false drawer.", told)
        project = Project.objects.get(kind=ProjectKind.RESEARCH, research_details__clue=self.clue)
        self.assertEqual(project.status, ProjectStatus.ACTIVE)
        self.assertEqual(project.owner_persona_id, persona_of(self.ysmay).pk)
        self.assertIn(f"project/check {project.pk}", told)
        self.assertIn(
            "That trail is already under investigation; lend your checks to it.",
            self.telnet(self.ysmay, "search start 1"),
        )


class OpeningAWindow(JourneyCase):
    """Ysmay keeps the parlor; its window opens and closes at her word and not at Hobb's."""

    def setUp(self) -> None:
        super().setUp()
        self.parlor = self.make_room("The Parlor")
        self.garden = self.make_room("The Garden")
        self.profile = RoomProfileFactory(objectdb=self.parlor)
        self.ysmay = self.make_player("Ysmay", room=self.parlor)
        self.hobb = self.make_player("Hobb", room=self.parlor)
        LocationTenancyFactory(
            room_profile=self.profile,
            tenant_persona=persona_of(self.ysmay),
            kind=LocationRole.TENANT,
        )
        self.window = self._exit("window", kind=ExitKind.WINDOW)
        self.door = self._exit("door", kind=ExitKind.DOOR)

    def _exit(self, name: str, *, kind: str):
        exit_obj = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.exits.Exit")
        exit_obj.location = self.parlor
        exit_obj.destination = self.garden
        exit_obj.save()
        profile = ExitProfile.get_or_create_for_exit(exit_obj)
        profile.exit_kind = kind
        profile.save(update_fields=["exit_kind"])
        return exit_obj

    def window_open(self) -> bool:
        return ExitProfile.objects.get(objectdb=self.window).is_open

    def test_the_tenant_opens_and_closes_it(self) -> None:
        self.assertIn("Open which exit?", self.telnet(self.ysmay, "open"))
        self.assertIn("Close which exit?", self.telnet(self.ysmay, "close"))
        self.assertIn("Could not find an exit called 'gate'.", self.telnet(self.ysmay, "open gate"))
        self.assertIn("That is not a window.", self.telnet(self.ysmay, "open door"))
        self.assertIn(
            "You don't have standing in that room.", self.telnet(self.hobb, "open window")
        )
        self.assertFalse(self.window_open())

        self.assertIn("You open window.", self.telnet(self.ysmay, "open window"))
        self.assertTrue(self.window_open())
        self.assertIn("You close window.", self.telnet(self.ysmay, "close window"))
        self.assertFalse(self.window_open())

        result = self.web(self.ysmay, "open_window", exit=self.window)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertTrue(self.window_open())
        result = self.web(self.hobb, "close_window", exit=self.window)
        self.assertFalse(result.detail.success)
        self.assertIn("You don't have standing in that room.", result.detail.message)
        self.assertTrue(self.window_open())


@override_settings(SEED_SAMPLE_CONTENT=True)
class GatheringTheLeavings(JourneyCase):
    """Ysmay cut a purse in the alley, and the theft left traces where it happened. She
    gathers them before anyone else can and makes them disappear. The Gather Evidence
    check is sample content; nothing on the web sends these verbs yet, so the dispatch
    seam is sent directly."""

    def setUp(self) -> None:
        super().setUp()
        seed_check_resolution_tables()
        seed_security_check_content()
        self.alley = self.make_room("The Back Alley")
        self.profile = RoomProfileFactory(objectdb=self.alley)
        self.street = self.make_room("Tanner's Row")
        self.ysmay = self.make_player("Ysmay", room=self.alley)
        self.hobb = self.make_player("Hobb", room=self.alley)
        fill_action_points(self.ysmay)
        fill_action_points(self.hobb)
        self.theft = CrimeKindFactory(slug="theft", name="Theft")

    def crime(self, title: str) -> CrimeEvidence:
        """A theft of Ysmay's done in the alley's scene, its evidence left there."""
        deed = LegendEntryFactory(
            persona=persona_of(self.ysmay), title=title, scene=SceneFactory(room=self.alley)
        )
        tag_deed_crimes(deed, [self.theft])
        return CrimeEvidence.objects.get(deed=deed)

    def roll(self, name: str, level: int):
        return force_check_outcome(CheckOutcomeFactory(name=name, success_level=level))

    def held_objects(self) -> list[str]:
        return sorted(obj.key for obj in self.ysmay.contents)

    def test_the_leavings_gathered_and_disposed_of(self) -> None:  # noqa: PLR0915 - one crime, read top to bottom
        usage = "Usage: evidence [gather [<id>] | dispose <id> | produce <#> | examine <id>]"
        self.assertIn(
            "No evidence of yours lies here, and you hold none.",
            self.telnet(self.ysmay, "evidence"),
        )
        self.assertIn(usage, self.telnet(self.ysmay, "evidence frob"))
        self.assertIn(usage, self.telnet(self.ysmay, "evidence gather x"))
        self.assertIn(usage, self.telnet(self.ysmay, "evidence dispose"))
        self.assertIn(
            "There's no such evidence.", self.telnet(self.ysmay, "evidence gather 999999")
        )
        self.assertIn(
            "Name the evidence: |wevidence gather <id>|n (see |wevidence|n).",
            self.telnet(self.ysmay, "evidence gather"),
        )

        evidence = self.crime("The Alley Purse")
        self.assertEqual(evidence.state, EvidenceState.AT_SCENE)
        told = self.telnet(self.ysmay, "evidence")
        self.assertIn("Your crime's leavings, here:", told)
        self.assertIn(f"  {evidence.pk}. traces of: The Alley Purse", told)
        self.assertNotIn("Evidence you hold:", told)
        # Hobb's crime it was not: he sees nothing of it and cannot be handed it by name.
        self.assertIn(
            "No evidence of yours lies here, and you hold none.", self.telnet(self.hobb, "evidence")
        )
        self.assertIn("Name the evidence:", self.telnet(self.hobb, "evidence gather"))

        # Gathering is done where the crime happened, on a Gather Evidence roll.
        self.ysmay.move_to(self.street, quiet=True)
        self.assertIn(
            "You must be standing where the crime happened to do that.",
            self.telnet(self.ysmay, f"evidence gather {evidence.pk}"),
        )
        self.ysmay.move_to(self.alley, quiet=True)
        with self.roll("Fumbled", -1) as capture:
            told = self.telnet(self.ysmay, "evidence gather")
        self.assertEqual(capture.check_type.name, "Gather Evidence")
        self.assertIn(
            "PLACEHOLDER You paw through the scene but come away with nothing usable.", told
        )
        self.assertEqual(CrimeEvidence.objects.get(pk=evidence.pk).state, EvidenceState.AT_SCENE)
        self.assertEqual(self.held_objects(), [])
        with self.roll("Pocketed", 1):
            told = self.telnet(self.ysmay, "evidence gather")
        self.assertIn("PLACEHOLDER You quietly pocket what the crime left behind.", told)
        evidence = CrimeEvidence.objects.get(pk=evidence.pk)
        self.assertEqual(evidence.state, EvidenceState.GATHERED)
        self.assertEqual(evidence.item_instance.holder_character_sheet_id, self.ysmay.sheet_data.pk)
        self.assertEqual(self.held_objects(), ["Incriminating evidence"])
        told = self.telnet(self.ysmay, "evidence")
        self.assertIn("Evidence you hold:", told)
        self.assertIn(f"  {evidence.pk}. The Alley Purse (Gathered)", told)
        self.assertNotIn("leavings", told)
        self.assertIn(
            "There is no evidence left to gather here.",
            self.telnet(self.ysmay, f"evidence gather {evidence.pk}"),
        )
        self.assertIn(
            "There's nothing produced to examine.",
            self.telnet(self.ysmay, f"evidence examine {evidence.pk}"),
        )
        self.assertIn(
            "You know of no filed cases with evidence to produce.",
            self.telnet(self.ysmay, "evidence produce"),
        )
        self.assertIn("No case #1.", self.telnet(self.ysmay, "evidence produce 1"))

        # Disposing of it is the holder's, on the same roll.
        self.assertIn(
            "You are not holding that evidence.",
            self.telnet(self.hobb, f"evidence dispose {evidence.pk}"),
        )
        self.assertIn(
            "There's no such evidence.", self.telnet(self.ysmay, "evidence dispose 999999")
        )
        with self.roll("Shaken", -1):
            told = self.telnet(self.ysmay, f"evidence dispose {evidence.pk}")
        self.assertIn(
            "PLACEHOLDER You can't quite bring yourself to make it disappear cleanly.", told
        )
        self.assertEqual(CrimeEvidence.objects.get(pk=evidence.pk).state, EvidenceState.GATHERED)
        item_pk = evidence.item_instance_id
        with self.roll("Burned", 1):
            told = self.telnet(self.ysmay, f"evidence dispose {evidence.pk}")
        self.assertIn("PLACEHOLDER The evidence is gone, as far as anyone can prove.", told)
        evidence = CrimeEvidence.objects.get(pk=evidence.pk)
        self.assertEqual(
            (evidence.state, evidence.item_instance_id), (EvidenceState.DISPOSED, None)
        )
        self.assertFalse(ItemInstance.objects.filter(pk=item_pk).exists())
        self.assertEqual(self.held_objects(), [])
        self.assertIn(
            "That evidence is beyond disposing of now.",
            self.telnet(self.ysmay, f"evidence dispose {evidence.pk}"),
        )
        self.assertIn(
            "No evidence of yours lies here, and you hold none.",
            self.telnet(self.ysmay, "evidence"),
        )

    def test_the_web_sends_the_evidence_by_id(self) -> None:
        evidence = self.crime("The Tanner's Strongbox")
        self.assertEqual(
            self.web(self.ysmay, "gather_evidence", evidence_id="7").detail.message,
            "There's no such evidence.",
        )
        self.assertEqual(
            self.web(self.ysmay, "gather_evidence", evidence_id=999999).detail.message,
            "There's no such evidence.",
        )
        self.assertEqual(
            self.web(self.ysmay, "dispose_evidence", evidence_id=evidence.pk).detail.message,
            "That evidence is beyond disposing of now.",
        )
        with self.roll("Pocketed", 1):
            result = self.web(self.ysmay, "gather_evidence", evidence_id=evidence.pk)
        self.assertEqual(
            result.detail.message, "PLACEHOLDER You quietly pocket what the crime left behind."
        )
        self.assertEqual(result.detail.data, {"evidence_id": evidence.pk})
        self.assertEqual(CrimeEvidence.objects.get(pk=evidence.pk).state, EvidenceState.GATHERED)
        self.assertEqual(
            self.web(self.hobb, "dispose_evidence", evidence_id=evidence.pk).detail.message,
            "You are not holding that evidence.",
        )
        self.assertEqual(
            self.web(self.ysmay, "examine_evidence", evidence_id=evidence.pk).detail.message,
            "There's nothing produced to examine.",
        )
        with self.roll("Burned", 1):
            result = self.web(self.ysmay, "dispose_evidence", evidence_id=evidence.pk)
        self.assertEqual(
            result.detail.message, "PLACEHOLDER The evidence is gone, as far as anyone can prove."
        )
        self.assertEqual(CrimeEvidence.objects.get(pk=evidence.pk).state, EvidenceState.DISPOSED)
        self.assertEqual(self.held_objects(), [])
