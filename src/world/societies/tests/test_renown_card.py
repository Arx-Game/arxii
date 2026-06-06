"""Tests for #744 — renown card view for foreign character sheets.

The renown card is what a viewer sees on someone else's sheet — a
limited surface filtered by what the viewer's persona's societies are
aware of. Per spec: tier label only on fame (no numeric reveal), deeds
visible iff ``societies_aware`` intersects viewer's society
memberships, reputation rows for the viewer's societies only.
"""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.societies.constants import FameTier
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocietyFactory,
)
from world.societies.models import LegendEntry, SocietyReputation
from world.societies.renown import set_persona_fame
from world.societies.renown_serializers import build_renown_card_payload


def _make_primary_persona():
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    return sheet.primary_persona


def _make_viewer_with_society():
    """Build a viewer persona with a membership in a known Society."""
    viewer = _make_primary_persona()
    society = SocietyFactory(name="House Viewer")
    org = OrganizationFactory(society=society)
    OrganizationMembershipFactory(persona=viewer, organization=org)
    return viewer, society


class RenownCardShapeTests(TestCase):
    def test_anonymous_viewer_clamps_tier_to_normal(self) -> None:
        """Per spec: 'essentially nothing visible' for an anonymous viewer.

        A viewer with no society context lacks the lens through which
        to read a Celebrity. Clamp to NORMAL.
        """
        target = _make_primary_persona()
        target.name = "Alice"
        target.save(update_fields=["name"])
        set_persona_fame(target, 1_500)  # actually CELEBRITY

        payload = build_renown_card_payload(target, viewer_persona=None)

        self.assertEqual(payload["persona_name"], "Alice")
        self.assertEqual(payload["fame"]["tier"], FameTier.NORMAL.value)
        self.assertEqual(payload["visible_deeds"], [])
        self.assertEqual(payload["visible_reputation"], [])


class VisibleDeedsTests(TestCase):
    def test_no_deeds_visible_when_viewer_has_no_society_memberships(self) -> None:
        target = _make_primary_persona()
        LegendEntry.objects.create(persona=target, title="Anon deed", base_value=10)
        bare_viewer = _make_primary_persona()  # no memberships

        payload = build_renown_card_payload(target, viewer_persona=bare_viewer)
        self.assertEqual(payload["visible_deeds"], [])

    def test_deeds_visible_when_societies_aware_intersects_viewer(self) -> None:
        target = _make_primary_persona()
        viewer, society = _make_viewer_with_society()
        deed = LegendEntry.objects.create(persona=target, title="Heard about it", base_value=30)
        deed.societies_aware.add(society)

        payload = build_renown_card_payload(target, viewer_persona=viewer)

        self.assertEqual(len(payload["visible_deeds"]), 1)
        self.assertEqual(payload["visible_deeds"][0]["title"], "Heard about it")

    def test_deeds_invisible_when_societies_aware_does_not_intersect(self) -> None:
        target = _make_primary_persona()
        viewer, _ = _make_viewer_with_society()
        other_society = SocietyFactory(name="House Stranger")
        deed = LegendEntry.objects.create(persona=target, title="Hidden deed", base_value=30)
        deed.societies_aware.add(other_society)

        payload = build_renown_card_payload(target, viewer_persona=viewer)
        self.assertEqual(payload["visible_deeds"], [])

    def test_masked_persona_with_zero_visible_deeds_surfaces_nothing(self) -> None:
        """A masked persona — viewer in a society that hasn't heard anything."""
        target = _make_primary_persona()
        viewer, _ = _make_viewer_with_society()
        # Target has a deed but it's aware to a different society.
        other = SocietyFactory(name="House Other")
        deed = LegendEntry.objects.create(persona=target, title="Cloaked", base_value=50)
        deed.societies_aware.add(other)

        payload = build_renown_card_payload(target, viewer_persona=viewer)

        self.assertEqual(payload["visible_deeds"], [])
        self.assertEqual(payload["visible_reputation"], [])


class VisibleReputationTests(TestCase):
    def test_reputation_filtered_to_viewer_societies_only(self) -> None:
        target = _make_primary_persona()
        viewer, viewer_society = _make_viewer_with_society()
        other_society = SocietyFactory(name="House Outsider")
        SocietyReputation.objects.create(persona=target, society=viewer_society, value=250)
        SocietyReputation.objects.create(persona=target, society=other_society, value=500)

        payload = build_renown_card_payload(target, viewer_persona=viewer)

        self.assertEqual(len(payload["visible_reputation"]), 1)
        self.assertEqual(payload["visible_reputation"][0]["society_name"], "House Viewer")


class PerceptionOffsetTests(TestCase):
    def test_viewer_society_offset_drops_tier(self) -> None:
        target = _make_primary_persona()
        set_persona_fame(target, 1_500)  # CELEBRITY tier index 2
        # Viewer's first society has offset -2 → tier drops to NORMAL.
        viewer = _make_primary_persona()
        insular = SocietyFactory(name="House Insular", fame_perception_offset=-2)
        org = OrganizationFactory(society=insular)
        OrganizationMembershipFactory(persona=viewer, organization=org)

        payload = build_renown_card_payload(target, viewer_persona=viewer)

        self.assertEqual(payload["fame"]["tier"], FameTier.NORMAL.value)

    def test_viewer_with_no_society_uses_raw_tier(self) -> None:
        target = _make_primary_persona()
        set_persona_fame(target, 12_000)  # HOUSEHOLD_NAME
        bare_viewer = _make_primary_persona()
        payload = build_renown_card_payload(target, viewer_persona=bare_viewer)
        self.assertEqual(payload["fame"]["tier"], FameTier.HOUSEHOLD_NAME.value)


class RenownCardEndpointTests(TestCase):
    """HTTP-level integration: permission + viewer_persona security gates."""

    def _build_account_with_persona(self, username: str):
        """Account + roster-tenured character with one primary persona."""
        from evennia_extensions.factories import AccountFactory
        from world.roster.factories import (
            PlayerDataFactory,
            RosterEntryFactory,
            RosterTenureFactory,
        )

        account = AccountFactory(username=username)
        player_data = PlayerDataFactory(account=account)
        character = CharacterFactory(db_key=f"{username}-char")
        sheet = CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet=sheet)
        RosterTenureFactory(
            roster_entry=entry,
            player_data=player_data,
            end_date=None,
        )
        return account, sheet.primary_persona

    def test_foreign_authenticated_viewer_can_read_card(self) -> None:
        """B1 — the canonical use case: alice looks at bob's sheet."""
        alice_account, alice_persona = self._build_account_with_persona("alice")
        _, bob_persona = self._build_account_with_persona("bob")
        self.client.force_login(alice_account)
        response = self.client.get(
            f"/api/personas/{bob_persona.pk}/renown-card/",
            {"viewer_persona": alice_persona.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["persona_id"], bob_persona.pk)

    def test_viewer_persona_belonging_to_other_account_403s(self) -> None:
        """B2 — alice cannot pass charlie's persona pk as viewer."""
        alice_account, _alice_persona = self._build_account_with_persona("alice2")
        _, bob_persona = self._build_account_with_persona("bob2")
        _, charlie_persona = self._build_account_with_persona("charlie2")
        self.client.force_login(alice_account)
        response = self.client.get(
            f"/api/personas/{bob_persona.pk}/renown-card/",
            {"viewer_persona": charlie_persona.pk},
        )
        self.assertEqual(response.status_code, 403)

    def test_nonexistent_viewer_persona_pk_400s(self) -> None:
        """H1 — bad pk should 400, not silently fall back to anonymous."""
        alice_account, _alice_persona = self._build_account_with_persona("alice3")
        _, bob_persona = self._build_account_with_persona("bob3")
        self.client.force_login(alice_account)
        response = self.client.get(
            f"/api/personas/{bob_persona.pk}/renown-card/",
            {"viewer_persona": 999_999},
        )
        self.assertEqual(response.status_code, 400)

    def test_non_integer_viewer_persona_400s(self) -> None:
        alice_account, _alice_persona = self._build_account_with_persona("alice4")
        _, bob_persona = self._build_account_with_persona("bob4")
        self.client.force_login(alice_account)
        response = self.client.get(
            f"/api/personas/{bob_persona.pk}/renown-card/",
            {"viewer_persona": "abc"},
        )
        self.assertEqual(response.status_code, 400)

    def test_no_viewer_persona_param_defaults_to_users_own_persona(self) -> None:
        """When the query param is omitted, the viewer resolves from request.user."""
        alice_account, alice_persona = self._build_account_with_persona("alice5")
        _, bob_persona = self._build_account_with_persona("bob5")
        # Wire alice into a society so something would be visible if she's the viewer.
        society = SocietyFactory(name="House Shared")
        org = OrganizationFactory(society=society)
        OrganizationMembershipFactory(persona=alice_persona, organization=org)
        deed = LegendEntry.objects.create(persona=bob_persona, title="Common deed", base_value=10)
        deed.societies_aware.add(society)
        self.client.force_login(alice_account)

        response = self.client.get(f"/api/personas/{bob_persona.pk}/renown-card/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["visible_deeds"]), 1)

    def test_unauthenticated_request_401s(self) -> None:
        _, bob_persona = self._build_account_with_persona("bob6")
        response = self.client.get(f"/api/personas/{bob_persona.pk}/renown-card/")
        self.assertIn(response.status_code, (401, 403))
