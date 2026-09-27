"""Look never shows a masked character's real description to someone who hasn't
seen through the mask (#4030, the look-path half of #1325)."""

from __future__ import annotations

import django.test

from actions.registry import get_action
from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PersonaDiscoveryFactory
from world.scenes.services import create_mask

REAL_DESC = "A tall woman with a crescent scar across her left cheek."


class LookMaskDescriptionTests(django.test.TestCase):
    def setUp(self) -> None:
        room = RoomProfileFactory().objectdb
        viewer_entry = RosterEntryFactory()
        self.viewer_sheet = viewer_entry.character_sheet
        self.viewer = self.viewer_sheet.character
        # Give the viewer a real account + current tenure — CharacterState's
        # viewer context (owned personas + discovery lookup) resolves off the
        # looker's account, the same wiring `test_look_persona_display.py` uses.
        viewer_account = AccountFactory()
        player_data, _ = PlayerData.objects.get_or_create(account=viewer_account)
        RosterTenureFactory(player_data=player_data, roster_entry=viewer_entry)
        self.viewer.db_account = viewer_account
        self.viewer.save()
        self.viewer.move_to(room, quiet=True)

        target_entry = RosterEntryFactory()
        self.target_sheet = target_entry.character_sheet
        self.target = self.target_sheet.character
        self.target.move_to(room, quiet=True)
        self.target_sheet.additional_desc = REAL_DESC
        self.target_sheet.save(update_fields=["additional_desc"])

    def _look(self, actor=None):
        return get_action("look").run(actor or self.viewer, target=self.target)

    def test_unmasked_target_shows_description(self) -> None:
        assert REAL_DESC in self._look().message

    def test_undiscovered_mask_hides_description_and_real_name(self) -> None:
        create_mask(self.target_sheet, name="stag mask")
        message = self._look().message
        assert REAL_DESC not in message
        assert self.target.key not in message

    def test_discovered_mask_shows_description(self) -> None:
        mask = create_mask(self.target_sheet, name="stag mask")
        PersonaDiscoveryFactory(
            persona=self.target_sheet.primary_persona,
            linked_to=mask,
            discovered_by=self.viewer_sheet,
        )
        assert REAL_DESC in self._look().message

    def test_self_look_shows_own_description_under_a_mask(self) -> None:
        create_mask(self.target_sheet, name="stag mask")
        result = get_action("look").run(self.target, target=self.target)
        assert REAL_DESC in result.message

    def test_staff_viewer_sees_description_under_a_mask(self) -> None:
        create_mask(self.target_sheet, name="stag mask")
        staff = AccountFactory(is_staff=True)
        self.viewer.db_account = staff
        self.viewer.save()
        assert REAL_DESC in self._look().message
