"""Whoever plays a story NPC is not offered templates the NPC cannot use (#4418)."""

from __future__ import annotations

from django.test import TestCase
from evennia.objects.models import ObjectDB

from actions.constants import ActionCategory, ActionTargetType
from actions.factories import ActionTemplateFactory
from actions.player_interface import _social_consent_exclusions, get_player_actions
from evennia_extensions.factories import ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
    make_general_category,
)
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.models.choices import RosterType
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Block


class NpcSceneActionsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.template = ActionTemplateFactory(
            name="Deceive",
            category=ActionCategory.SOCIAL,
            target_type=ActionTargetType.SINGLE,
        )
        cls.pc = CharacterSheetFactory().character
        npc_entry = RosterEntryFactory(roster__roster_type=RosterType.NPC)
        cls.npc = npc_entry.character_sheet.character

    def _names(self, character) -> set[str]:
        return {a.display_name for a in get_player_actions(character)}

    def test_npc_is_not_offered_unresisted_templates(self) -> None:
        self.assertNotIn("Deceive", self._names(self.npc))
        self.assertIn("Deceive", self._names(self.pc))

    def test_npc_is_offered_the_template_once_authored(self) -> None:
        self.template.resist_check_type = CheckTypeFactory()
        self.template.consent_category = make_general_category()
        self.template.save()
        self.assertIn("Deceive", self._names(self.npc))

    def test_npc_is_not_offered_an_untagged_template_even_with_a_resist(self) -> None:
        self.template.resist_check_type = CheckTypeFactory()
        self.template.save()
        self.assertNotIn("Deceive", self._names(self.npc))


class StoryNpcTargetingConsentTests(TestCase):
    """A story NPC skips a PC's consent exclusion only where the PC cannot refuse (#4418)."""

    def setUp(self) -> None:
        self.room = ObjectDBFactory(db_key="Parlour")
        npc_entry = RosterEntryFactory(roster__roster_type=RosterType.NPC)
        self.npc_char = npc_entry.character_sheet.character
        self.npc_tenure = RosterTenureFactory(roster_entry=npc_entry, end_date=None)
        pc_entry = RosterEntryFactory(roster__roster_type=RosterType.ACTIVE)
        self.pc_tenure = RosterTenureFactory(roster_entry=pc_entry, end_date=None)
        self.pc_persona_ids = set(pc_entry.character_sheet.personas.values_list("pk", flat=True))
        ObjectDB.objects.filter(pk=self.npc_char.pk).update(db_location=self.room)
        self.npc_char.db_location = self.room
        scene = SceneFactory(room=self.room, is_active=True)
        for tenure in (self.npc_tenure, self.pc_tenure):
            SceneParticipationFactory(scene=scene, account=tenure.player_data.account)
        self.pref = SocialConsentPreferenceFactory(tenure=self.pc_tenure)
        self.romantic = SocialConsentCategoryFactory(key="romantic", name="Romantic")
        self.romantic.refusable_from_npcs = True
        self.romantic.save()

    def _opt_out(self, category) -> None:
        SocialConsentCategoryRuleFactory(
            preference=self.pref, category=category, mode=ConsentMode.ALLOWLIST
        )

    def test_a_child_of_a_refusable_category_keeps_the_exclusion(self) -> None:
        child = SocialConsentCategoryFactory(
            key="courtship", name="Courtship", parent=self.romantic
        )
        self._opt_out(child)
        excluded = _social_consent_exclusions(self.npc_char, child)
        self.assertTrue(self.pc_persona_ids <= excluded)

    def test_a_category_players_cannot_refuse_skips_the_exclusion(self) -> None:
        hostile = SocialConsentCategoryFactory(key="hostile", name="Hostile")
        self._opt_out(hostile)
        self.assertFalse(self.pc_persona_ids & _social_consent_exclusions(self.npc_char, hostile))

    def test_a_block_still_applies_where_consent_is_skipped(self) -> None:
        hostile = SocialConsentCategoryFactory(key="hostile", name="Hostile")
        Block.objects.create(
            owner=self.pc_tenure.player_data,
            blocked_player=self.npc_tenure.player_data,
            account_level=True,
        )
        excluded = _social_consent_exclusions(self.npc_char, hostile)
        self.assertTrue(self.pc_persona_ids <= excluded)
