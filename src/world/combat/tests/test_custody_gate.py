"""Tests for the custody APPEAR gate on ``add_opponent`` (#2001 Task 5).

Covers: an outsider GM is refused (disclosure-safe message) when spawning a
story-protected NPC's persona/existing_objectdb into combat; a participant
GM, staff, and an APPEAR-scoped clearance all pass; ``acting_account=None``
(the system-initiated carve-out used by duels/cast_seed/magic-summon/
companion-materialize callers) skips the check entirely; and a freshly
created ephemeral CombatNPC is never gated (it has no CharacterSheet).
"""

from evennia.utils.test_resources import EvenniaTestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, ThreatPoolFactory
from world.combat.scaling import NPCUnderCustodyError
from world.combat.services import add_opponent
from world.gm.factories import GMProfileFactory, GMTableFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import PersonaFactory
from world.stories.constants import CustodyClearanceStatus, CustodyScope
from world.stories.factories import (
    CustodyClearanceFactory,
    StoryFactory,
    StoryParticipationFactory,
    StoryProtectedSubjectFactory,
)
from world.stories.types import StoryStatus


def _account_playing(character_sheet):
    """An AccountDB currently playing character_sheet's character (live tenure)."""
    entry = RosterEntryFactory(character_sheet=character_sheet)
    player_data = PlayerDataFactory()
    RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return player_data.account


class AddOpponentCustodyGateTests(EvenniaTestCase):
    def setUp(self):
        super().setUp()
        self.story = StoryFactory(status=StoryStatus.ACTIVE)
        self.custodian_gm = GMProfileFactory()
        table = GMTableFactory(gm=self.custodian_gm)
        self.story.primary_table = table
        self.story.save(update_fields=["primary_table"])

        self.persona = PersonaFactory()
        self.npc_sheet = self.persona.character_sheet
        self.protection = StoryProtectedSubjectFactory(
            story=self.story, subject_sheet=self.npc_sheet
        )

        self.encounter = CombatEncounterFactory()
        self.pool = ThreatPoolFactory()

    def _add(self, **kwargs):
        return add_opponent(
            self.encounter,
            name="Protected NPC",
            tier="mook",
            max_health=20,
            threat_pool=self.pool,
            persona=self.persona,
            **kwargs,
        )

    def test_outsider_gm_refused_with_disclosure_message(self):
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        with self.assertRaises(NPCUnderCustodyError) as ctx:
            self._add(acting_account=outsider_account)

        expected = (
            "This NPC is under another story's custody — request clearance "
            f"from GM {self.custodian_gm.account.username}."
        )
        self.assertEqual(ctx.exception.user_message, expected)
        self.assertEqual(str(ctx.exception), expected)

    def test_orphaned_story_staff_fallback_message(self):
        # A protecting story with no primary_table has no custodian GM to
        # name. Uses a persona guarded ONLY by the orphaned story — the setUp
        # protection has a named custodian and, being older, would otherwise
        # be the reported blocker.
        orphaned_story = StoryFactory(status=StoryStatus.ACTIVE)
        orphan_persona = PersonaFactory()
        StoryProtectedSubjectFactory(
            story=orphaned_story, subject_sheet=orphan_persona.character_sheet
        )
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        with self.assertRaises(NPCUnderCustodyError) as ctx:
            add_opponent(
                self.encounter,
                name="Orphan-story NPC",
                tier="mook",
                max_health=20,
                threat_pool=self.pool,
                persona=orphan_persona,
                acting_account=outsider_account,
            )

        expected = (
            "This NPC is under another story's custody — request clearance "
            "from the story's GM via staff."
        )
        self.assertEqual(ctx.exception.user_message, expected)

    def test_participant_gm_allowed(self):
        participant_sheet = CharacterSheetFactory()
        participant_account = _account_playing(participant_sheet)
        StoryParticipationFactory(story=self.story, character=participant_sheet.character)

        opp = self._add(acting_account=participant_account)
        self.assertIsNotNone(opp)
        self.assertEqual(opp.objectdb, self.persona.character_sheet.character)

    def test_appear_clearance_allowed(self):
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)
        outsider_gm_profile = GMProfileFactory(account=outsider_account)
        CustodyClearanceFactory(
            protected_subject=self.protection,
            requested_by=outsider_gm_profile,
            scope=CustodyScope.APPEAR,
            status=CustodyClearanceStatus.GRANTED,
        )

        opp = self._add(acting_account=outsider_account)
        self.assertIsNotNone(opp)

    def test_staff_allowed(self):
        staff_account = AccountFactory(is_staff=True)
        opp = self._add(acting_account=staff_account)
        self.assertIsNotNone(opp)

    def test_acting_account_none_skips_check(self):
        # Mirrors the system-initiated callers (duels.py/cast_seed.py/magic
        # summon effect handlers/companion materialize): they never pass
        # acting_account, so the protected persona's opponent is created
        # unblocked even though an outsider account would be refused above.
        opp = self._add()
        self.assertIsNotNone(opp)

    def test_fresh_ephemeral_spawn_ungated(self):
        outsider_sheet = CharacterSheetFactory()
        outsider_account = _account_playing(outsider_sheet)

        opp = add_opponent(
            self.encounter,
            name="Random Mook",
            tier="mook",
            max_health=15,
            threat_pool=self.pool,
            acting_account=outsider_account,
        )
        self.assertTrue(opp.objectdb_is_ephemeral)
