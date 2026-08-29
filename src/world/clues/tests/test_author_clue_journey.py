"""``author_clue`` -> ``staff_place_clue`` -> ``search`` discovery journey (#3432).

End-to-end self-service authoring loop: staff mints a SECRET-target ``Clue`` via
``author_clue`` (Decision 1a -- SECRET targets are staff-only for now), places it in a
room via ``staff_place_clue``, and a player's ``search`` finds it and is granted the
secret's knowledge. Exercises the same ``action.run()`` dispatch seam telnet and web
both use for the mint + place steps (registry dispatch), not the service functions
directly. The search step follows the precedent set by
``actions.tests.test_investigation.SearchThenDisarmJourneyTest`` and calls
``SearchAction().execute()`` directly rather than through ``run()`` -- that test class
established this to sidestep AP/fatigue-pool setup unrelated to the discovery seam
this journey is actually proving.
"""

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.definitions.investigation import SearchAction
from actions.registry import get_action
from evennia_extensions.factories import AccountFactory, CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.constants import SEARCH_CHECK_TYPE_NAME, ClueTargetKind
from world.clues.models import Clue, RoomClue
from world.roster.factories import RosterEntryFactory
from world.secrets.factories import SecretFactory
from world.secrets.models import SecretKnowledge
from world.traits.factories import CheckOutcomeFactory


def _staff_actor(db_key: str) -> ObjectDB:
    """A Character whose account is staff, with a working CharacterSheet (mirrors
    ``actions.tests.test_world_builder_actions._staff_actor``)."""
    char = CharacterFactory(db_key=db_key)
    account = AccountFactory(username=f"acct_{db_key}", is_staff=True)
    char.db_account = account
    char.save()
    CharacterSheetFactory(character=char)
    return char


class AuthorClueThenPlaceThenSearchJourneyTest(TestCase):
    def setUp(self) -> None:
        CheckTypeFactory(name=SEARCH_CHECK_TYPE_NAME)
        self.staff = _staff_actor("JourneyStaff")
        self.secret = SecretFactory()
        self.room_profile = RoomProfileFactory()
        self.room = self.room_profile.objectdb

        self.searcher_entry = RosterEntryFactory()
        self.searcher = self.searcher_entry.character_sheet.character
        self.searcher.move_to(self.room, quiet=True)

        self.hit = CheckOutcomeFactory(name="Journey-Author-Search-Hit", success_level=1)

    def test_authored_then_placed_secret_clue_is_discovered_and_grants_knowledge(self) -> None:
        author_result = get_action("author_clue").run(
            self.staff,
            name="A Dark Rumor",
            description="Something whispered near the well.",
            target_kind=ClueTargetKind.SECRET,
            target_id=self.secret.pk,
        )
        assert author_result.success, author_result.message
        slug = author_result.data["slug"]
        clue = Clue.objects.get(slug=slug)
        assert clue.target_secret_id == self.secret.pk

        place_result = get_action("staff_place_clue").run(
            self.staff,
            room_id=self.room_profile.objectdb_id,
            clue_slug=slug,
        )
        assert place_result.success, place_result.message
        assert RoomClue.objects.filter(room_profile=self.room_profile, clue=clue).exists()

        with force_check_outcome(self.hit):
            search_result = SearchAction().execute(self.searcher)

        assert search_result.success, search_result.message
        assert clue.name in search_result.message
        assert SecretKnowledge.objects.filter(
            roster_entry=self.searcher_entry, secret=self.secret
        ).exists()
