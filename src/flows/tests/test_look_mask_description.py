"""Look never shows a masked character's real description to someone who hasn't
seen through the mask (#4030, the look-path half of #1325)."""

from __future__ import annotations

import django.test

from actions.registry import get_action
from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from evennia_extensions.models import PlayerData
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaDiscoveryFactory, PersonaFactory
from world.scenes.services import create_mask, set_active_persona

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

    def test_established_active_persona_hides_description_from_a_stranger(self) -> None:
        # A named (non-fake-name) ESTABLISHED persona still hides the link to the
        # real character from a stranger -- ``identity_revealed_to_viewer`` only
        # reveals a non-fake-name persona when it is PRIMARY (#4030 review).
        established = PersonaFactory(
            character_sheet=self.target_sheet,
            persona_type=PersonaType.ESTABLISHED,
            is_fake_name=False,
        )
        set_active_persona(self.target_sheet, established)
        assert REAL_DESC not in self._look().message

    def test_established_active_persona_shows_description_to_owner_and_staff(self) -> None:
        established = PersonaFactory(
            character_sheet=self.target_sheet,
            persona_type=PersonaType.ESTABLISHED,
            is_fake_name=False,
        )
        set_active_persona(self.target_sheet, established)
        result = get_action("look").run(self.target, target=self.target)
        assert REAL_DESC in result.message

        staff = AccountFactory(is_staff=True)
        self.viewer.db_account = staff
        self.viewer.save()
        assert REAL_DESC in self._look().message

    def test_alternate_active_persona_hides_description_from_a_stranger(self) -> None:
        alternate = PersonaFactory(
            character_sheet=self.target_sheet,
            persona_type=PersonaType.ALTERNATE,
            is_fake_name=False,
        )
        set_active_persona(self.target_sheet, alternate)
        assert REAL_DESC not in self._look().message

    def test_alternate_active_persona_shows_description_to_owner_and_staff(self) -> None:
        alternate = PersonaFactory(
            character_sheet=self.target_sheet,
            persona_type=PersonaType.ALTERNATE,
            is_fake_name=False,
        )
        set_active_persona(self.target_sheet, alternate)
        result = get_action("look").run(self.target, target=self.target)
        assert REAL_DESC in result.message

        staff = AccountFactory(is_staff=True)
        self.viewer.db_account = staff
        self.viewer.save()
        assert REAL_DESC in self._look().message

    def test_sheet_with_no_persona_shows_description_without_raising(self) -> None:
        # ``CharacterState._identity_revealed_to``'s ``except Persona.DoesNotExist:
        # return True`` branch (#4030 review, controller ruling: keep behaviour) --
        # a sheet with no persona at all has no mask to protect, matching
        # ``_presented_persona_name``/``_resolve_presented_identity``.
        no_persona_roster = RosterEntryFactory(character_sheet__primary_persona=False)
        no_persona_sheet = no_persona_roster.character_sheet
        no_persona_target = no_persona_sheet.character
        no_persona_target.move_to(self.viewer.location, quiet=True)
        no_persona_sheet.additional_desc = REAL_DESC
        no_persona_sheet.save(update_fields=["additional_desc"])

        result = get_action("look").run(self.viewer, target=no_persona_target)
        assert REAL_DESC in result.message
