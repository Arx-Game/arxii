"""PERSONA_LINK clue (#2120) — the Clue-based in-game producer for PersonaDiscovery.

Mirrors ``test_rescue_clue.py``'s plant/grant/search journey shape. PersonaDiscovery
previously had zero in-game producer (only the test factory / django admin created
rows) — this is the wiring that lets a planted, story-gated clue pierce a masked
persona through the existing Search/trigger/research acquisition machinery.
"""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.constants import ClueTargetKind
from world.clues.models import Clue, RoomClue
from world.clues.services import grant_clue_target, search_room
from world.roster.factories import RosterEntryFactory
from world.scenes.factories import PersonaFactory
from world.scenes.models import PersonaDiscovery
from world.scenes.persona_display import resolve_display_for_viewer
from world.traits.factories import CheckOutcomeFactory


def _mask_and_real():
    """A masked persona and its real (primary) identity, on the same character sheet."""
    finder = RosterEntryFactory()
    sheet = finder.character_sheet
    mask = PersonaFactory(character_sheet=sheet, is_fake_name=True, name="raven mask")
    return sheet, mask


class GrantPersonaLinkTargetTests(TestCase):
    def test_grant_creates_a_normalized_persona_discovery(self) -> None:
        sheet, mask = _mask_and_real()
        real = sheet.primary_persona
        clue = Clue.objects.create(
            target_kind=ClueTargetKind.PERSONA_LINK,
            target_persona=mask,
            target_persona_linked=real,
            name="A signet ring",
            description="PLACEHOLDER",
        )
        discoverer = RosterEntryFactory()

        grant_clue_target(clue, discoverer)

        lower, higher = sorted([mask, real], key=lambda p: p.pk)
        discovery = PersonaDiscovery.objects.get(discovered_by=discoverer.character_sheet)
        assert discovery.persona_id == lower.pk
        assert discovery.linked_to_id == higher.pk

    def test_grant_is_idempotent(self) -> None:
        sheet, mask = _mask_and_real()
        real = sheet.primary_persona
        clue = Clue.objects.create(
            target_kind=ClueTargetKind.PERSONA_LINK,
            target_persona=mask,
            target_persona_linked=real,
            name="x",
            description="y",
        )
        discoverer = RosterEntryFactory()

        grant_clue_target(clue, discoverer)
        grant_clue_target(clue, discoverer)

        assert (
            PersonaDiscovery.objects.filter(discovered_by=discoverer.character_sheet).count() == 1
        )

    def test_grant_is_noop_when_untargeted(self) -> None:
        clue = Clue(target_kind=ClueTargetKind.PERSONA_LINK, name="x", description="y")
        discoverer = RosterEntryFactory()

        grant_clue_target(clue, discoverer)

        assert not PersonaDiscovery.objects.exists()


class SearchFindsPersonaLinkClueTests(TestCase):
    def test_search_pierces_the_mask_for_the_discoverer_only(self) -> None:
        """Plant -> search -> reveal journey, with a non-discoverer negative (leak table).

        A stranger who never searched must not see the reveal — piercing is
        GM-authored (a planted, story-gated evidence trail), never an automatic
        check against an arbitrary masked character (ADR-0033).
        """
        sheet, mask = _mask_and_real()
        real = sheet.primary_persona
        room = RoomProfileFactory()
        clue = Clue.objects.create(
            target_kind=ClueTargetKind.PERSONA_LINK,
            target_persona=mask,
            target_persona_linked=real,
            name="A signet ring",
            description="PLACEHOLDER",
        )
        RoomClue.objects.create(room_profile=room, clue=clue, detect_difficulty=0)

        discoverer = RosterEntryFactory()
        non_discoverer = RosterEntryFactory()
        search_check = CheckTypeFactory(name="Search")

        with force_check_outcome(CheckOutcomeFactory(name="Hit", success_level=3)):
            found = search_room(discoverer.character_sheet.character, room, search_check)

        assert len(found) == 1
        assert PersonaDiscovery.objects.filter(discovered_by=discoverer.character_sheet).exists()

        display_name, is_discovered = resolve_display_for_viewer(
            mask,
            viewer_persona_ids=set(),
            viewer_sheet_ids={discoverer.character_sheet.pk},
        )
        assert is_discovered
        assert display_name == f"{mask.name} ({real.name})"

        other_name, other_discovered = resolve_display_for_viewer(
            mask,
            viewer_persona_ids=set(),
            viewer_sheet_ids={non_discoverer.character_sheet.pk},
        )
        assert not other_discovered
        assert other_name != display_name
