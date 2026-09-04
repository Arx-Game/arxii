"""Account-level caches for roster entries, personas, codex knowledge and covenant
memberships (#3597, ADR-0260), and the related-model writes that clear them."""

from django.test import TestCase
from django.utils import timezone

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.services import grant_codex_entry
from world.covenants.factories import CharacterCovenantRoleFactory, CovenantFactory
from world.covenants.services import leave_covenant
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.constants import PersonaType
from world.scenes.services import create_persona


class AccountCacheTests(TestCase):
    """Each cache is computed once, then cleared by the write that changes its answer."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()
        self.account = AccountFactory()
        self.player_data = PlayerDataFactory(account=self.account)
        self.sheet = CharacterSheetFactory()
        self.roster_entry = RosterEntryFactory(character_sheet=self.sheet)
        self.tenure = RosterTenureFactory(
            player_data=self.player_data, roster_entry=self.roster_entry, end_date=None
        )

    def tearDown(self) -> None:
        # The identity map shares this Account instance with the next test; never
        # leave a cache computed against rows the rollback is about to remove.
        self.account.clear_cached_properties()

    def test_cached_roster_entries_lists_current_tenures(self) -> None:
        self.assertEqual(self.account.cached_roster_entries, [self.roster_entry])
        with self.assertNumQueries(0):
            self.account.cached_roster_entries  # noqa: B018

    def test_cached_persona_ids_includes_every_persona_type(self) -> None:
        primary = self.sheet.primary_persona
        self.assertEqual(self.account.cached_persona_ids, [primary.pk])
        mask = create_persona(self.sheet, name="Veil", persona_type=PersonaType.TEMPORARY)
        self.assertEqual(sorted(self.account.cached_persona_ids), sorted([primary.pk, mask.pk]))

    def test_cached_codex_knowledge_reflects_a_grant_made_after_warmup(self) -> None:
        self.assertEqual(self.account.cached_codex_knowledge, {})
        entry = CodexEntryFactory(is_public=False)
        grant_codex_entry(self.roster_entry, entry)
        known = self.account.cached_codex_knowledge[self.roster_entry.pk][entry.pk]
        self.assertEqual(known.status, CodexKnowledgeStatus.KNOWN)
        self.assertEqual(known.roster_entry_id, self.roster_entry.pk)
        self.assertEqual(known.character_name, self.sheet.character.name)

    def test_cached_covenant_memberships_clears_on_leave(self) -> None:
        covenant = CovenantFactory()
        membership = CharacterCovenantRoleFactory(character_sheet=self.sheet, covenant=covenant)
        self.assertIs(self.account.cached_covenant_memberships[covenant.pk], membership)
        leave_covenant(membership=membership)
        self.assertNotIn(covenant.pk, self.account.cached_covenant_memberships)

    def test_cached_covenant_memberships_first_wins_by_pk(self) -> None:
        covenant = CovenantFactory()
        first = CharacterCovenantRoleFactory(character_sheet=self.sheet, covenant=covenant)
        other_sheet = CharacterSheetFactory()
        other_entry = RosterEntryFactory(character_sheet=other_sheet)
        RosterTenureFactory(player_data=self.player_data, roster_entry=other_entry, end_date=None)
        CharacterCovenantRoleFactory(character_sheet=other_sheet, covenant=covenant)
        self.assertIs(self.account.cached_covenant_memberships[covenant.pk], first)

    def test_ending_a_tenure_clears_every_cache(self) -> None:
        covenant = CovenantFactory()
        CharacterCovenantRoleFactory(character_sheet=self.sheet, covenant=covenant)
        grant_codex_entry(self.roster_entry, CodexEntryFactory(is_public=False))
        self.assertTrue(self.account.cached_roster_entries)
        self.assertTrue(self.account.cached_persona_ids)
        self.assertTrue(self.account.cached_codex_knowledge)
        self.assertTrue(self.account.cached_covenant_memberships)

        self.tenure.end_date = timezone.now()
        self.tenure.save()

        self.assertEqual(self.account.cached_roster_entries, [])
        self.assertEqual(self.account.cached_persona_ids, [])
        self.assertEqual(self.account.cached_codex_knowledge, {})
        self.assertEqual(self.account.cached_covenant_memberships, {})

    def test_get_available_roster_entries_matches_available_characters(self) -> None:
        entries = self.account.get_available_roster_entries()
        self.assertEqual(entries, [self.roster_entry])
        self.assertEqual(
            [entry.character_sheet.character for entry in entries],
            self.account.get_available_characters(),
        )
