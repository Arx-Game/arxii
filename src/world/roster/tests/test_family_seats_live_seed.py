"""The seat picker's live-server seed (#5130) writes what `frontend/e2e/family-seats.spec.ts`
reads.

The real-test CI job runs ``seed_family_seats_spec`` against a throwaway Postgres database
and a browser reads the result; this runs the seed on the SQLite tier and asks the same
endpoints the page asks, so a broken seed shows up before that job does.
"""

from __future__ import annotations

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from integration_tests.live_seeds import seed_family_seats_spec
from world.character_creation.constants import Stage
from world.character_creation.models import CharacterDraft
from world.roster.constants import RelationshipType


class FamilySeatsLiveSeedTests(APITestCase):
    def test_seed_is_idempotent_and_the_page_reads_a_house_with_two_seats(self) -> None:
        account = AccountFactory(username="e2e_family_seats_account")

        first = seed_family_seats_spec(username="e2e_family_seats_account")
        second = seed_family_seats_spec(username="e2e_family_seats_account")
        self.assertEqual(first, second)

        draft = CharacterDraft.objects.get(pk=first.draft_id)
        self.assertEqual(draft.current_stage, Stage.LINEAGE)
        template = draft.selected_origin_template
        kinds = list(template.claimable_kinds.values_list("pk", flat=True))

        self.client.force_authenticate(user=account)
        # The family list as the Lineage stage asks for it.
        listed = self.client.get(
            "/api/character-creation/families/",
            {"area_id": draft.selected_area_id, "kind": kinds},
        ).json()
        offered = {row["name"]: row["has_open_seat"] for row in listed}
        self.assertEqual(
            offered, {first.family_name: True, first.closed_family_name: False}, listed
        )

        seats = self.client.get(f"/api/roster/families/{first.family_id}/slots/").json()
        self.assertEqual(seats["head_name"], first.head_name)
        self.assertEqual(
            {
                row["id"]: (row["name"], row["name_locked"], row["head_relation"])
                for row in seats["slots"]
            },
            {
                first.locked_seat_id: (first.locked_seat_name, True, RelationshipType.CHILD),
                first.open_seat_id: (first.open_seat_name, False, RelationshipType.NIECE_NEPHEW),
            },
        )

        # The two saves the spec makes, and what the draft says after each.
        url = f"/api/character-creation/drafts/{first.draft_id}/"
        lineage = str(int(Stage.LINEAGE))
        body = self.client.patch(url, {"family_id": first.family_id}, format="json").json()
        self.assertEqual(body["stage_errors"][lineage], ["Choose your place in the family"])
        body = self.client.patch(
            url, {"claimed_kin_slot_id": first.locked_seat_id}, format="json"
        ).json()
        self.assertEqual(body["claimed_kin_slot"], first.locked_seat_id)
        self.assertEqual(body["stage_errors"].get(lineage, []), [])
