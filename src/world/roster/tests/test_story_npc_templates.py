"""Template story NPCs count against no cap; ordinary ones still do (#4418)."""

from django.test import TestCase

from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, seed_default_gm_level_caps
from world.roster.services.staff_characters import StaffMintError, mint_story_npc


class StoryNPCTemplateCapTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        seed_default_gm_level_caps()
        cls.gm = GMProfileFactory(level=GMLevel.JUNIOR).account
        mint_story_npc(gm_account=cls.gm, name="Rook One")
        mint_story_npc(gm_account=cls.gm, name="Rook Two")

    def test_template_mints_for_a_gm_at_cap(self) -> None:
        character = mint_story_npc(gm_account=self.gm, name="Guard Template", as_template=True)
        entry = character.sheet_data.roster_entry
        assert entry.story_npc_settings.is_template
        assert entry.created_by_account == self.gm
        assert entry.current_tenure is None

    def test_ordinary_mint_at_cap_is_refused(self) -> None:
        with self.assertRaisesMessage(StaffMintError, "You already have 2 story NPC(s)"):
            mint_story_npc(gm_account=self.gm, name="Rook Three")
