"""Endpoint tests for the GM character-finalize flow (#1506, hardened #3268).

POST /api/character-creation/drafts/<pk>/finalize-gm/ — a player-GM finalizes a draft
onto the Available roster for a table they own, stamped with GM_TABLE provenance.
"""

from __future__ import annotations

from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from world.character_creation.models import CharacterDraft
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory, GMTableFactory, seed_default_gm_level_caps
from world.magic.exceptions import GiftResonanceUnresolvable
from world.roster.models import RosterEntry, RosterTenure
from world.roster.models.choices import CreationProvenance, RosterType


class GMFinalizeViewTests(FinalizationTestMixin, APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls._setup_finalization_base(cls, prefix="GM Finalize", height_min=700, height_max=800)
        cls.gm = GMProfileFactory()
        cls.table = GMTableFactory(gm=cls.gm)

    def _url(self, draft) -> str:
        return f"/api/character-creation/drafts/{draft.pk}/finalize-gm/"

    def _draft(self, account=None, **extra_draft_data):
        # _create_base_draft (FinalizationTestMixin) builds a fully submittable
        # draft, reusing the same CG prerequisites/tradition/gift/technique/resonance
        # fixtures the service-level finalization tests use (#3268 Decision 3) —
        # finalize_gm now gates on draft.can_submit() same as add_to_roster.
        self.account = account or self.gm.account
        return self._create_base_draft(first_name="Aurelius", **extra_draft_data)

    def test_owner_finalizes_with_gm_table_provenance(self) -> None:
        draft = self._draft()
        self.client.force_authenticate(user=self.gm.account)
        response = self.client.post(
            self._url(draft),
            {"target_table": self.table.pk, "story_title": "The Grand Design"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        entry = RosterEntry.objects.get(pk=response.data["roster_entry_id"])
        self.assertEqual(entry.creation_provenance, CreationProvenance.GM_TABLE)
        self.assertEqual(entry.created_for_table, self.table)
        self.assertEqual(entry.created_by_account, self.gm.account)
        # Match the typed key (#2728), never the display label.
        self.assertEqual(entry.roster.roster_type, RosterType.AVAILABLE)

    def test_non_owner_of_the_table_is_forbidden(self) -> None:
        other_gm = GMProfileFactory()
        draft = self._draft(account=other_gm.account)
        self.client.force_authenticate(user=other_gm.account)
        response = self.client.post(
            self._url(draft),
            {"target_table": self.table.pk, "story_title": "Not Mine"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_story_title_returns_400(self) -> None:
        draft = self._draft()
        self.client.force_authenticate(user=self.gm.account)
        response = self.client.post(
            self._url(draft),
            {"target_table": self.table.pk},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unknown_table_returns_404(self) -> None:
        draft = self._draft()
        self.client.force_authenticate(user=self.gm.account)
        response = self.client.post(
            self._url(draft),
            {"target_table": 999999, "story_title": "Ghost Table"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_incomplete_draft_returns_400_with_incomplete_stages_detail(self) -> None:
        """An incomplete draft is rejected before any mutation (#3268) — mirrors the
        completeness gate finalize_character (and thus add_to_roster) already enforces.
        """
        draft = CharacterDraft.objects.create(
            account=self.gm.account,
            selected_area=self.area,
            selected_beginnings=self.beginnings,
            selected_origin_template=self.unknown_upbringing,
            selected_species=self.species,
            selected_gender=self.gender,
            age=25,
            birthday_month=6,
            birthday_day=12,
            height_band=self.height_band,
            height_inches=750,
            build=self.build,
            draft_data={
                "first_name": "Half Finished",
                "tarot_card_name": self.tarot_card.name,
                "tarot_reversed": False,
                "path_skills_complete": True,
                "traits_complete": True,
                "magic_complete": True,
                # No stats field - attributes stage incomplete
            },
        )
        self.client.force_authenticate(user=self.gm.account)
        response = self.client.post(
            self._url(draft),
            {"target_table": self.table.pk, "story_title": "Unfinished Business"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertIn("incomplete stages", response.data["detail"])

    def test_claim_as_npc_lands_on_npc_shelf_with_tenure(self) -> None:
        """#3426: claim_as_npc=true binds the entry to the finalizing GM by tenure."""
        self.gm.level = GMLevel.JUNIOR
        self.gm.save(update_fields=["level"])
        seed_default_gm_level_caps()

        draft = self._draft()
        self.client.force_authenticate(user=self.gm.account)
        response = self.client.post(
            self._url(draft),
            {
                "target_table": self.table.pk,
                "story_title": "My Own NPC",
                "claim_as_npc": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        entry = RosterEntry.objects.get(pk=response.data["roster_entry_id"])
        self.assertEqual(entry.roster.roster_type, RosterType.NPC)
        self.assertEqual(entry.creation_provenance, CreationProvenance.GM_TABLE)
        tenure = RosterTenure.objects.get(roster_entry=entry)
        self.assertEqual(tenure.player_data.account_id, self.gm.account_id)
        self.assertIsNone(tenure.end_date)

    def test_claim_as_npc_refused_below_junior(self) -> None:
        """A STARTING-level GM (the factory default) can't claim_as_npc yet (#3426)."""
        seed_default_gm_level_caps()
        draft = self._draft()
        self.client.force_authenticate(user=self.gm.account)
        response = self.client.post(
            self._url(draft),
            {
                "target_table": self.table.pk,
                "story_title": "Too Junior",
                "claim_as_npc": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertFalse(RosterEntry.objects.filter(created_for_table=self.table).exists())

    def test_unresolvable_gift_resonance_returns_400_not_500(self) -> None:
        """A GiftResonanceUnresolvable from finalize_gm_character must not surface as an
        unhandled 500 — mirrors add_to_roster's #2971 handling exactly.
        """
        draft = self._draft()
        self.client.force_authenticate(user=self.gm.account)

        with patch(
            "world.character_creation.services.finalize_gm_character",
            side_effect=GiftResonanceUnresolvable,
        ):
            response = self.client.post(
                self._url(draft),
                {"target_table": self.table.pk, "story_title": "Unresolvable Resonance"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.content)
        self.assertEqual(response.data["detail"], "Character creation failed.")
