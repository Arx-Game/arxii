"""Tests for Resonance Pivot Spec A Phase 16 API surface (§4.5, §5.6).

Covers:
- ThreadViewSet (list / retrieve / create / soft-retire destroy + ownership)
- ThreadPullPreviewView (POST preview, never mutates state)
- RitualPerformView (Imbuing dispatch path + typed-exception → 400)
- ThreadWeavingTeachingOfferViewSet (read-only list + target_kind filter)
- IsThreadOwner permission enforcement
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory, ObjectDBFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory
from world.magic.constants import EffectKind, TargetKind, VitalBonusTarget
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterResonanceFactory,
    CharacterThreadWeavingUnlockFactory,
    ImbuingRitualFactory,
    IntensityTierFactory,
    ResonanceFactory,
    RitualFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    ThreadWeavingTeachingOfferFactory,
    ThreadWeavingUnlockFactory,
    WeavingCeremonyFactory,
)
from world.magic.models import PendingRitualEffect, Thread
from world.roster.factories import RosterTenureFactory
from world.traits.factories import TraitFactory


def _link_account_to_sheet(account, character, sheet):
    """Tie an AccountDB to a CharacterSheet via an active RosterTenure.

    Also sets character.account so that service functions that navigate
    character_sheet.character.account resolve correctly.
    """
    character.account = account
    account.characters.add(character)
    return RosterTenureFactory(
        roster_entry__character_sheet=sheet,
        player_data__account=account,
    )


class ThreadViewSetTests(APITestCase):
    """Tests for Thread list / retrieve / create / destroy (Spec A §4.5)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="thread_owner")
        cls.character = CharacterFactory(db_key="ThreadOwner")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.other_account = AccountFactory(username="thread_other")
        cls.other_character = CharacterFactory(db_key="ThreadOther")
        cls.other_sheet = CharacterSheetFactory(character=cls.other_character)
        _link_account_to_sheet(cls.other_account, cls.other_character, cls.other_sheet)

        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_trait=cls.trait,
            level=5,
        )
        # WeaveThreadAction requires PendingRitualEffect for Rite of Weaving.
        # Seed the canonical ceremony ritual so setUp can create per-test effects.
        cls.weaving_ritual = WeavingCeremonyFactory()

    def setUp(self) -> None:
        # Each test that POSTs /threads/ (creating a Thread) needs a fresh
        # PendingRitualEffect — it's consumed on the first successful weave.
        # Idempotent: delete any leftover from a prior test before creating.
        PendingRitualEffect.objects.filter(
            character=self.sheet,
            ritual=self.weaving_ritual,
        ).delete()
        PendingRitualEffect.objects.create(
            character=self.sheet,
            ritual=self.weaving_ritual,
        )

    def test_list_requires_auth(self) -> None:
        response = self.client.get(reverse("magic:thread-list"))
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_list_returns_only_owned_threads(self) -> None:
        other_thread = ThreadFactory(
            owner=self.other_sheet,
            resonance=self.resonance,
            target_trait=TraitFactory(),
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(reverse("magic:thread-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned = {t["id"] for t in response.data["results"]}
        self.assertIn(self.thread.pk, returned)
        self.assertNotIn(other_thread.pk, returned)

    def test_list_excludes_retired(self) -> None:
        retired = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_trait=TraitFactory(),
        )
        retired.retired_at = retired.created_at  # any non-null value
        retired.save(update_fields=["retired_at"])
        self.client.force_authenticate(user=self.account)
        response = self.client.get(reverse("magic:thread-list"))
        returned = {t["id"] for t in response.data["results"]}
        self.assertNotIn(retired.pk, returned)

    def test_retrieve_requires_ownership(self) -> None:
        self.client.force_authenticate(user=self.other_account)
        response = self.client.get(reverse("magic:thread-detail", args=[self.thread.pk]))
        # queryset filter already strips it → 404.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_delegates_to_weave_thread(self) -> None:
        trait = TraitFactory()
        CharacterThreadWeavingUnlockFactory(
            character=self.sheet,
            unlock=ThreadWeavingUnlockFactory(
                target_kind=TargetKind.TRAIT,
                unlock_trait=trait,
            ),
        )
        self.client.force_authenticate(user=self.account)
        payload = {
            "resonance": self.resonance.pk,
            "target_kind": TargetKind.TRAIT,
            "target_id": trait.pk,
            "character_sheet_id": self.sheet.pk,
            "name": "Bound to Steel",
        }
        response = self.client.post(
            reverse("magic:thread-list"),
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(
            Thread.objects.filter(
                owner=self.sheet,
                resonance=self.resonance,
                target_trait=trait,
            ).exists()
        )

    def test_create_rejects_without_weaving_unlock(self) -> None:
        trait = TraitFactory()
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.TRAIT,
                "target_id": trait.pk,
                "character_sheet_id": self.sheet.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_foreign_character_sheet_id(self) -> None:
        """An account cannot weave threads for another account's sheet."""
        trait = TraitFactory()
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.TRAIT,
                "target_id": trait.pk,
                "character_sheet_id": self.other_sheet.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_requires_character_sheet_id(self) -> None:
        """Accounts with zero owned sheets get a clean 400, not a 500."""
        empty_account = AccountFactory(username="thread_empty")
        self.client.force_authenticate(user=empty_account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.TRAIT,
                "target_id": TraitFactory().pk,
                # No character_sheet_id — required field, expect 400.
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_destroy_soft_retires(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.delete(
            reverse("magic:thread-detail", args=[self.thread.pk]),
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.thread.refresh_from_db()
        self.assertIsNotNone(self.thread.retired_at)
        # Row still exists — historical references preserved.
        self.assertTrue(Thread.objects.filter(pk=self.thread.pk).exists())

    # ------------------------------------------------------------------
    # FACET thread creation tests
    # ------------------------------------------------------------------

    def test_create_facet_thread_succeeds_with_global_unlock(self) -> None:
        """A character with a global FACET weaving unlock can create a FACET thread."""
        from world.magic.factories import FacetFactory
        from world.magic.models import ThreadWeavingUnlock

        facet = FacetFactory()
        # Global FACET unlock — no typed FK required; bypass full_clean() via .objects.create()
        unlock = ThreadWeavingUnlock.objects.create(target_kind=TargetKind.FACET, xp_cost=100)
        CharacterThreadWeavingUnlockFactory(character=self.sheet, unlock=unlock)

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.FACET,
                "target_id": facet.pk,
                "character_sheet_id": self.sheet.pk,
                "name": "Silk Thread",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(
            Thread.objects.filter(
                owner=self.sheet,
                resonance=self.resonance,
                target_facet=facet,
                target_kind=TargetKind.FACET,
            ).exists()
        )

    def test_create_facet_thread_unknown_facet_id_returns_400(self) -> None:
        """POSTing a non-existent facet pk returns 400 with a descriptive message."""
        from world.magic.models import ThreadWeavingUnlock

        unlock = ThreadWeavingUnlock.objects.create(target_kind=TargetKind.FACET, xp_cost=100)
        CharacterThreadWeavingUnlockFactory(character=self.sheet, unlock=unlock)

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.FACET,
                "target_id": 999999,
                "character_sheet_id": self.sheet.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("FACET", str(response.data))

    # ------------------------------------------------------------------
    # RELATIONSHIP_TRACK ownership tests (#2033)
    # ------------------------------------------------------------------

    def test_create_relationship_track_thread_succeeds_for_own_row(self) -> None:
        """Weaving the CALLER's own track-progress row toward a named partner works.

        ``target_id`` is the ``RelationshipTrack`` **catalog** id (#2159) — no API
        exposes a ``RelationshipTrackProgress`` pk (``RelationshipTrackProgressSerializer``
        has no id field), so the old contract of addressing the progress row directly by
        pk was structurally unreachable from the web. The fix adds ``target_persona_id``
        (same convention as ``RelationshipUpdateViewSet``) to name the partner, then
        resolves via ``(relationship__source=<caller>, relationship__target=<partner>,
        track_id=<catalog id>)`` — mirroring telnet's ``CmdWeaveThread._resolve_track_anchor``.
        """
        from world.relationships.factories import (
            CharacterRelationshipFactory,
            RelationshipTrackFactory,
            RelationshipTrackProgressFactory,
        )

        track = RelationshipTrackFactory()
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_track=track,
        )
        CharacterThreadWeavingUnlockFactory(character=self.sheet, unlock=unlock)

        partner_sheet = CharacterSheetFactory()
        own_relationship = CharacterRelationshipFactory(source=self.sheet, target=partner_sheet)
        own_progress = RelationshipTrackProgressFactory(
            relationship=own_relationship, track=track, developed_points=10
        )

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.RELATIONSHIP_TRACK,
                "target_id": track.pk,
                "target_persona_id": partner_sheet.primary_persona.pk,
                "character_sheet_id": self.sheet.pk,
                "name": "Bound to Marcus",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(
            Thread.objects.filter(owner=self.sheet, target_relationship_track=own_progress).exists()
        )

    def test_create_relationship_track_thread_selects_right_partner_row(self) -> None:
        """Two partners sharing the same track: the named partner's row is woven, not either.

        Both partner relationships develop the SAME catalog track; the resolver must key
        off ``target_persona_id`` to pick the correct ``RelationshipTrackProgress`` row.
        """
        from world.relationships.factories import (
            CharacterRelationshipFactory,
            RelationshipTrackFactory,
            RelationshipTrackProgressFactory,
        )

        track = RelationshipTrackFactory()
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_track=track,
        )
        CharacterThreadWeavingUnlockFactory(character=self.sheet, unlock=unlock)

        partner_a_sheet = CharacterSheetFactory()
        partner_b_sheet = CharacterSheetFactory()
        relationship_a = CharacterRelationshipFactory(source=self.sheet, target=partner_a_sheet)
        relationship_b = CharacterRelationshipFactory(source=self.sheet, target=partner_b_sheet)
        RelationshipTrackProgressFactory(
            relationship=relationship_a, track=track, developed_points=5
        )
        progress_b = RelationshipTrackProgressFactory(
            relationship=relationship_b, track=track, developed_points=10
        )

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.RELATIONSHIP_TRACK,
                "target_id": track.pk,
                "target_persona_id": partner_b_sheet.primary_persona.pk,
                "character_sheet_id": self.sheet.pk,
                "name": "Bound to Partner B",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(
            Thread.objects.filter(owner=self.sheet, target_relationship_track=progress_b).exists()
        )

    def test_create_relationship_track_thread_missing_partner_returns_400(self) -> None:
        """Omitting ``target_persona_id`` for RELATIONSHIP_TRACK is a validation error."""
        from world.relationships.factories import RelationshipTrackFactory

        track = RelationshipTrackFactory()
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_track=track,
        )
        CharacterThreadWeavingUnlockFactory(character=self.sheet, unlock=unlock)

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.RELATIONSHIP_TRACK,
                "target_id": track.pk,
                "character_sheet_id": self.sheet.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("target_persona_id is required", str(response.data))

    def test_create_relationship_track_thread_absent_progress_returns_friendly_message(
        self,
    ) -> None:
        """No developed history with the named partner on that track → a friendly message.

        Never a raw model DoesNotExist / oracle-style "does not exist" for a row shape the
        caller can't otherwise address — mirrors telnet's
        ``CmdWeaveThread._resolve_track_anchor`` wording.
        """
        from world.relationships.factories import RelationshipTrackFactory

        track = RelationshipTrackFactory(name="Trust")
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_track=track,
        )
        CharacterThreadWeavingUnlockFactory(character=self.sheet, unlock=unlock)

        # A partner sheet with no CharacterRelationship (let alone track progress)
        # toward self.sheet at all.
        partner_sheet = CharacterSheetFactory()

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.RELATIONSHIP_TRACK,
                "target_id": track.pk,
                "target_persona_id": partner_sheet.primary_persona.pk,
                "character_sheet_id": self.sheet.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertIn("You have no developed 'Trust' track with", str(response.data))
        self.assertNotIn("does not exist", str(response.data))

    def test_create_capstone_thread_unaffected_by_track_persona_change(self) -> None:
        """RELATIONSHIP_CAPSTONE keeps resolving by its own real pk (#2159 scope check).

        Only RELATIONSHIP_TRACK gained the ``target_persona_id`` requirement; a capstone
        anchor is still addressed directly by id, scoped to the caller's own relationship
        as before (#2033), with no partner kwarg needed.
        """
        from world.relationships.factories import (
            CharacterRelationshipFactory,
            RelationshipCapstoneFactory,
            RelationshipTrackFactory,
        )

        # ThreadWeavingUnlock has no CAPSTONE kind (DB constraint) — a RELATIONSHIP_TRACK
        # unlock for the capstone's own track satisfies weave_thread's unlock check for
        # RELATIONSHIP_CAPSTONE anchors (mirrors test_soul_tether_services
        # ._grant_relationship_track_unlock).
        track = RelationshipTrackFactory()
        unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_track=track,
        )
        CharacterThreadWeavingUnlockFactory(character=self.sheet, unlock=unlock)

        own_relationship = CharacterRelationshipFactory(
            source=self.sheet, target=CharacterSheetFactory()
        )
        capstone = RelationshipCapstoneFactory(relationship=own_relationship, track=track)

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.RELATIONSHIP_CAPSTONE,
                "target_id": capstone.pk,
                "character_sheet_id": self.sheet.pk,
                "name": "Sworn Bond",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Thread.objects.filter(owner=self.sheet, target_capstone=capstone).exists())

    # ------------------------------------------------------------------
    # COVENANT_ROLE thread creation tests
    # ------------------------------------------------------------------

    def test_create_covenant_role_thread_succeeds_when_held(self) -> None:
        """A character who has held a covenant role can create a COVENANT_ROLE thread."""
        from world.covenants.factories import CharacterCovenantRoleFactory, CovenantRoleFactory

        # Use a fresh account+character+sheet to avoid cached_property state from setUpTestData.
        account = AccountFactory(username="cr_thread_held")
        character = CharacterFactory(db_key="CRThreadHeld")
        sheet = CharacterSheetFactory(character=character)
        _link_account_to_sheet(account, character, sheet)

        role = CovenantRoleFactory()
        CharacterCovenantRoleFactory(character_sheet=sheet, covenant_role=role)

        # WeaveThreadAction requires a pending Rite of Weaving effect.
        PendingRitualEffect.objects.create(character=sheet, ritual=self.weaving_ritual)

        self.client.force_authenticate(user=account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.COVENANT_ROLE,
                "target_id": role.pk,
                "character_sheet_id": sheet.pk,
                "name": "Vanguard Thread",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(
            Thread.objects.filter(
                owner=sheet,
                resonance=self.resonance,
                target_covenant_role=role,
                target_kind=TargetKind.COVENANT_ROLE,
            ).exists()
        )

    def test_create_covenant_role_thread_never_held_returns_400(self) -> None:
        """A character who has never held the role gets a 400 with user_message."""
        from world.covenants.exceptions import CovenantRoleNeverHeldError
        from world.covenants.factories import CovenantRoleFactory

        role = CovenantRoleFactory()

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.COVENANT_ROLE,
                "target_id": role.pk,
                "character_sheet_id": self.sheet.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(CovenantRoleNeverHeldError.user_message, str(response.data))

    def test_create_covenant_role_thread_unknown_id_returns_400(self) -> None:
        """POSTing a non-existent CovenantRole pk returns 400 with a descriptive message."""
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.COVENANT_ROLE,
                "target_id": 999999,
                "character_sheet_id": self.sheet.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("COVENANT_ROLE", str(response.data))

    # ------------------------------------------------------------------
    # MANTLE threads (#512)
    # ------------------------------------------------------------------

    def test_create_mantle_thread_without_clearance_returns_400(self) -> None:
        """Weaving a MANTLE thread without level-1 clearance gets a 400 with user_message."""
        from world.items.factories import MantleFactory
        from world.magic.exceptions import MantleNotClearedError

        mantle = MantleFactory()

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.MANTLE,
                "target_id": mantle.pk,
                "character_sheet_id": self.sheet.pk,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(MantleNotClearedError.user_message, str(response.data))

    def test_create_mantle_thread_succeeds_with_clearance(self) -> None:
        """A character who has cleared the mantle's first rank can weave a MANTLE thread."""
        from world.items.factories import MantleFactory
        from world.items.services.mantle import grant_mantle_clearance

        # Fresh account+character+sheet to avoid cached_property state from setUpTestData.
        account = AccountFactory(username="mantle_thread_cleared")
        character = CharacterFactory(db_key="MantleThreadCleared")
        sheet = CharacterSheetFactory(character=character)
        _link_account_to_sheet(account, character, sheet)

        mantle = MantleFactory()
        grant_mantle_clearance(sheet, mantle, 1)
        sheet.character.mantle_clearances.invalidate()

        # WeaveThreadAction requires a pending Rite of Weaving effect.
        PendingRitualEffect.objects.create(character=sheet, ritual=self.weaving_ritual)

        self.client.force_authenticate(user=account)
        response = self.client.post(
            reverse("magic:thread-list"),
            {
                "resonance": self.resonance.pk,
                "target_kind": TargetKind.MANTLE,
                "target_id": mantle.pk,
                "character_sheet_id": sheet.pk,
                "name": "Banner Thread",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(
            Thread.objects.filter(
                owner=sheet,
                resonance=self.resonance,
                target_mantle=mantle,
                target_kind=TargetKind.MANTLE,
            ).exists()
        )

    # ------------------------------------------------------------------
    # Cap fields: path_cap, anchor_cap, effective_cap (Task 16)
    # ------------------------------------------------------------------

    def test_retrieve_includes_cap_fields(self) -> None:
        """GET /api/magic/threads/{id}/ includes path_cap, anchor_cap, effective_cap."""
        self.client.force_authenticate(user=self.account)
        response = self.client.get(
            reverse("magic:thread-detail", args=[self.thread.pk]),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("path_cap", response.data)
        self.assertIn("anchor_cap", response.data)
        self.assertIn("effective_cap", response.data)

    def test_retrieve_cap_fields_are_integers_for_trait_thread(self) -> None:
        """Cap fields are integers for a TRAIT thread (TRAIT has a CharacterTraitValue)."""
        from world.traits.factories import CharacterTraitValueFactory

        # Wire a CharacterTraitValue so compute_anchor_cap returns a real number.
        CharacterTraitValueFactory(
            character=self.sheet,
            trait=self.trait,
            value=3,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.get(
            reverse("magic:thread-detail", args=[self.thread.pk]),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        # anchor_cap = trait.value = 3; path_cap ≥ 10 (stage 0 → min 1 × 10)
        self.assertIsInstance(response.data["path_cap"], int)
        self.assertIsInstance(response.data["anchor_cap"], int)
        self.assertEqual(response.data["anchor_cap"], 3)
        self.assertIsInstance(response.data["effective_cap"], int)
        # effective_cap = min(path_cap, anchor_cap)
        self.assertEqual(
            response.data["effective_cap"],
            min(response.data["path_cap"], response.data["anchor_cap"]),
        )

    def test_list_includes_cap_fields(self) -> None:
        """GET /api/magic/threads/ list rows also expose cap fields."""
        self.client.force_authenticate(user=self.account)
        response = self.client.get(reverse("magic:thread-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"]
        self.assertTrue(len(results) >= 1)
        first = results[0]
        self.assertIn("path_cap", first)
        self.assertIn("anchor_cap", first)
        self.assertIn("effective_cap", first)


class ThreadPullPreviewTests(APITestCase):
    """Tests for POST /api/magic/thread-pull-preview/ (Spec A §5.6)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="preview_owner")
        cls.character = CharacterFactory(db_key="PreviewOwner")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_trait=cls.trait,
            level=20,
        )
        cls.cost = ThreadPullCostFactory(
            tier=1,
            resonance_cost=3,
            anima_per_thread=2,
        )
        cls.char_resonance = CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=10,
            lifetime_earned=10,
        )
        CharacterAnimaFactory(character=cls.character, current=10, maximum=10)

        # A tier-0 FLAT_BONUS gives a non-empty resolved_effects list.
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=cls.resonance,
            tier=0,
            flat_bonus_amount=2,
        )

    def test_requires_auth(self) -> None:
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {},
            format="json",
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_preview_returns_costs_and_effects(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["resonance_cost"], 3)
        # n_threads - 1 = 0 → anima_cost = 0
        self.assertEqual(response.data["anima_cost"], 0)
        self.assertTrue(response.data["affordable"])
        self.assertGreaterEqual(len(response.data["resolved_effects"]), 1)

    def test_preview_rejects_foreign_thread(self) -> None:
        other_sheet = CharacterSheetFactory(character=CharacterFactory(db_key="other"))
        foreign = ThreadFactory(
            owner=other_sheet,
            resonance=self.resonance,
            target_trait=TraitFactory(),
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [foreign.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_preview_rejects_bad_tier(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 9,  # > max_value=3
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_preview_capped_intensity_flag(self) -> None:
        IntensityTierFactory(name="Minor", threshold=1)
        # min_thread_level=5 keeps this row distinct from the tier-0 row
        # seeded in setUpTestData (which uses min_thread_level=0).
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            tier=0,
            min_thread_level=5,
            effect_kind=EffectKind.INTENSITY_BUMP,
            intensity_bump_amount=50,
            flat_bonus_amount=None,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["capped_intensity"])

    def test_preview_does_not_mutate(self) -> None:
        before_balance = self.char_resonance.balance
        self.client.force_authenticate(user=self.account)
        self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )
        self.char_resonance.refresh_from_db()
        self.assertEqual(self.char_resonance.balance, before_balance)

    def test_preview_marks_vital_bonus_inactive_in_non_combat_context(self) -> None:
        """Per spec §5.6 inactive flag + §3.8 ephemeral VITAL_BONUS rules.

        When the preview runs without a combat_encounter_id (ephemeral / RP
        context), any VITAL_BONUS resolved effect must be flagged inactive
        with scaled_value=0 and a non-empty inactive_reason so the UI can
        explain why the bonus isn't applied.
        """
        # Wire a tier-1 VITAL_BONUS row at min_thread_level=5 so the
        # (kind, resonance, tier, min_thread_level) unique key differs from
        # the tier-0 FLAT_BONUS row seeded in setUpTestData.
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=self.resonance,
            tier=1,
            min_thread_level=5,
            as_vital_bonus=True,
            vital_bonus_amount=4,
            vital_target=VitalBonusTarget.MAX_HEALTH,
            flat_bonus_amount=None,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
                # No action_context → ephemeral / RP (non-combat) context.
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        vital_rows = [
            r for r in response.data["resolved_effects"] if r["kind"] == EffectKind.VITAL_BONUS
        ]
        self.assertEqual(len(vital_rows), 1)
        self.assertTrue(vital_rows[0]["inactive"])
        self.assertEqual(vital_rows[0]["scaled_value"], 0)
        self.assertTrue(vital_rows[0]["inactive_reason"])

    def test_preview_rejects_foreign_character_sheet_id(self) -> None:
        """An account cannot preview pulls for another account's sheet."""
        foreign_account = AccountFactory(username="preview_foreign")
        foreign_character = CharacterFactory(db_key="PreviewForeign")
        foreign_sheet = CharacterSheetFactory(character=foreign_character)
        _link_account_to_sheet(foreign_account, foreign_character, foreign_sheet)
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "character_sheet_id": foreign_sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_preview_requires_character_sheet_id(self) -> None:
        """Accounts with zero owned sheets get a clean 400, not a 500."""
        empty_account = AccountFactory(username="preview_empty")
        self.client.force_authenticate(user=empty_account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                # No character_sheet_id — required field, expect 400.
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [self.thread.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def _build_relationship_track_pull(self, *, threaded_sheet_db_key: str):
        """Build a RELATIONSHIP_TRACK thread (owned by self.sheet, anchored to a
        relationship with a fresh third-party sheet) plus the tuning + effect
        rows needed for relationship-bond pull modulation (#1849) to fire.

        Mirrors world.magic.tests.test_pull_modulation_relationship's
        ``_relationship_track_thread`` helper + direct-trigger fixture.
        """
        from world.magic.models import RelationshipBondPullTuning
        from world.relationships.factories import (
            CharacterRelationshipFactory,
            RelationshipTrackProgressFactory,
        )

        threaded_sheet = CharacterSheetFactory(
            character=CharacterFactory(db_key=threaded_sheet_db_key)
        )
        relationship = CharacterRelationshipFactory(
            source=self.sheet, target=threaded_sheet, is_active=True, is_pending=False
        )
        progress = RelationshipTrackProgressFactory(relationship=relationship, developed_points=30)
        RelationshipBondPullTuning.objects.create(pk=1, coefficient=1, cap=20, half_saturation=30)

        rt_thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.resonance,
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            target_relationship_track=progress,
            target_trait=None,
            level=10,
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            resonance=self.resonance,
            tier=1,
            min_thread_level=0,
            effect_kind=EffectKind.FLAT_BONUS,
            flat_bonus_amount=4,
        )
        return rt_thread, threaded_sheet

    def test_preview_with_relationship_track_target_matches_commit_time_modulation(self) -> None:
        """#2035: the preview must surface the same relationship-bond-modulated
        amount spend_resonance_for_pull would grant at commit time (via
        resolve_pull_effects(target=...)) — not the raw unmodulated authored
        value the pre-fix preview always showed.
        """
        from world.magic.services.resonance import resolve_pull_effects

        rt_thread, threaded_sheet = self._build_relationship_track_pull(
            threaded_sheet_db_key="ThreadedY"
        )
        # Live target IS the threaded person Y — direct trigger (#1849).
        target_persona = threaded_sheet.primary_persona

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [rt_thread.pk],
                "action_context": {"target_persona_id": target_persona.pk},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # Compute the expected modulated amount the exact same way the commit
        # path (spend_resonance_for_pull -> resolve_pull_effects) would.
        expected = resolve_pull_effects(
            [rt_thread], tier=1, in_combat=False, target=threaded_sheet.character
        )
        expected_flat = next(r for r in expected if r.kind == EffectKind.FLAT_BONUS)

        flat_rows = [
            r for r in response.data["resolved_effects"] if r["kind"] == EffectKind.FLAT_BONUS
        ]
        self.assertEqual(len(flat_rows), 1)
        self.assertEqual(flat_rows[0]["scaled_value"], expected_flat.scaled_value)
        # Sanity: this must be the MODULATED value (14), not the raw authored
        # value (4) — proves the preview is no longer blind to the cast target.
        self.assertEqual(flat_rows[0]["scaled_value"], 14)

    def test_preview_without_target_leaves_relationship_track_pull_unmodulated(self) -> None:
        """Target-less preview stays byte-identical to the pre-#2035 behavior."""
        rt_thread, _threaded_sheet = self._build_relationship_track_pull(
            threaded_sheet_db_key="ThreadedY2"
        )

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [rt_thread.pk],
                # No action_context / target_persona_id -> unmodulated.
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        flat_rows = [
            r for r in response.data["resolved_effects"] if r["kind"] == EffectKind.FLAT_BONUS
        ]
        self.assertEqual(len(flat_rows), 1)
        self.assertEqual(flat_rows[0]["scaled_value"], 4)

    def test_preview_ignores_target_when_not_perceivable(self) -> None:
        """#2035 privacy guard: an unperceivable live target must not modulate the
        preview — this is a free, repeatable, uncommitted read (unlike the
        commit path), so it must not become an oracle for probing private
        relationship facts about personas the requester cannot perceive
        (mirrors pull_applicability.py's can_perceive gates, ADR-0086).
        """

        rt_thread, threaded_sheet = self._build_relationship_track_pull(
            threaded_sheet_db_key="ThreadedY3"
        )
        target_persona = threaded_sheet.primary_persona

        # Put the requester's and the target's characters in different,
        # unconnected rooms so can_perceive returns False.
        owner_room = ObjectDBFactory(
            db_key="PreviewOwnerRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        target_room = ObjectDBFactory(
            db_key="PreviewTargetRoom", db_typeclass_path="typeclasses.rooms.Room"
        )
        self.sheet.character.location = owner_room
        threaded_sheet.character.location = target_room

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {
                "character_sheet_id": self.sheet.pk,
                "resonance_id": self.resonance.pk,
                "tier": 1,
                "thread_ids": [rt_thread.pk],
                "action_context": {"target_persona_id": target_persona.pk},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        flat_rows = [
            r for r in response.data["resolved_effects"] if r["kind"] == EffectKind.FLAT_BONUS
        ]
        self.assertEqual(len(flat_rows), 1)
        # Unperceivable target silently degrades to the unmodulated preview.
        self.assertEqual(flat_rows[0]["scaled_value"], 4)


class RitualPerformViewTests(APITestCase):
    """Tests for POST /api/magic/rituals/perform/."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.account = AccountFactory(username="ritual_owner")
        cls.character = CharacterFactory(db_key="RitualOwner")
        cls.sheet = CharacterSheetFactory(character=cls.character)
        _link_account_to_sheet(cls.account, cls.character, cls.sheet)

        cls.resonance = ResonanceFactory()
        cls.trait = TraitFactory()
        cls.thread = ThreadFactory(
            owner=cls.sheet,
            resonance=cls.resonance,
            target_trait=cls.trait,
            level=2,
            _trait_value=9,  # anchor cap 9 — plenty of headroom under level 10
        )
        cls.char_resonance = CharacterResonanceFactory(
            character_sheet=cls.sheet,
            resonance=cls.resonance,
            balance=20,
            lifetime_earned=20,
        )
        cls.ritual = ImbuingRitualFactory()

    def test_requires_auth(self) -> None:
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {},
            format="json",
        )
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_imbuing_ceremony_web_post_fuses_perform_and_finisher(self) -> None:
        """One web POST performs the CEREMONY AND applies the imbue (2026-07 audit).

        The old contract only minted the PendingRitualEffect and silently
        dropped thread/amount — a dead state, since the web has no separate
        finisher UI (the telnet ``imbue`` command is the CEREMONY finisher).
        """
        self.client.force_authenticate(user=self.account)
        starting_level = self.thread.level
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.ritual.pk,
                "kwargs": {"thread_id": self.thread.pk, "amount": 5},
                "components": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["ritual_id"], self.ritual.pk)
        self.assertEqual(response.data["execution_kind"], "CEREMONY")
        self.assertIn("result", response.data)
        self.thread.refresh_from_db()
        self.assertGreater(self.thread.level, starting_level)
        # The finisher consumed the pending effect the perform minted.
        self.assertFalse(
            PendingRitualEffect.objects.filter(
                character=self.sheet,
                ritual=self.ritual,
            ).exists(),
        )

    def test_imbuing_ceremony_requires_thread_kwargs(self) -> None:
        """A bare imbuing perform 400s — the web has no finisher to consume it."""
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.ritual.pk,
                "kwargs": {},
                "components": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_imbuing_ceremony_duplicate_returns_400(self) -> None:
        """A second Rite of Imbuing before the first is consumed returns 400."""
        # Create a pending effect first (as if ceremony was already done once).
        PendingRitualEffect.objects.create(character=self.sheet, ritual=self.ritual)
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.ritual.pk,
                "kwargs": {"thread_id": self.thread.pk, "amount": 5},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_action_failure_returns_400_not_500(self) -> None:
        """An ACTION-level failure returns 400, not 500.

        Verify the HTTP contract: when PerformRitualAction returns a failure result
        (here: duplicate CEREMONY before the first is consumed), the view responds
        with 400 + a detail message, never 500.
        """
        # Pre-create the pending effect so the second attempt fails.
        PendingRitualEffect.objects.get_or_create(
            character=self.sheet,
            ritual=self.ritual,
        )
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.ritual.pk,
                "kwargs": {},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_kwargs_rejects_non_primitive_values(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.ritual.pk,
                "kwargs": {"thread_id": self.thread.pk, "extra": [1, 2, 3]},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ritual_rejects_foreign_character_sheet_id(self) -> None:
        """An account cannot dispatch rituals using another account's sheet."""
        foreign_account = AccountFactory(username="ritual_foreign")
        foreign_character = CharacterFactory(db_key="RitualForeign")
        foreign_sheet = CharacterSheetFactory(character=foreign_character)
        _link_account_to_sheet(foreign_account, foreign_character, foreign_sheet)
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "character_sheet_id": foreign_sheet.pk,
                "ritual_id": self.ritual.pk,
                "kwargs": {"thread_id": self.thread.pk, "amount": 5},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ritual_requires_character_sheet_id(self) -> None:
        """Accounts with zero owned sheets get a clean 400, not a 500."""
        empty_account = AccountFactory(username="ritual_empty")
        self.client.force_authenticate(user=empty_account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                # No character_sheet_id — required field, expect 400.
                "ritual_id": self.ritual.pk,
                "kwargs": {"thread_id": self.thread.pk, "amount": 5},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ritual_perform_rejects_foreign_owned_component(self) -> None:
        """A component ItemInstance held by a DIFFERENT character's sheet is
        rejected with 400, not a 500 crash.

        Regression for the final-review Finding 2 fold-in:
        ``RitualPerformRequestSerializer.validate()`` used to reference
        ``inst.owner_id``, a field that does not exist on ``ItemInstance``
        (only ``holder_character_sheet`` does) — this branch's own new work
        (wiring touchstone-mode consumption into ``PerformRitualAction``)
        makes this reachable via a real component requirement, so the
        ownership check must actually work rather than crash.
        """
        foreign_account = AccountFactory(username="ritual_component_foreign")
        foreign_character = CharacterFactory(db_key="RitualComponentForeign")
        foreign_sheet = CharacterSheetFactory(character=foreign_character)
        _link_account_to_sheet(foreign_account, foreign_character, foreign_sheet)
        foreign_item = ItemInstanceFactory(holder_character_sheet=foreign_sheet)

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.ritual.pk,
                "kwargs": {},
                "components": [foreign_item.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_ritual_perform_accepts_own_component(self) -> None:
        """A component ItemInstance the requester genuinely holds is accepted
        (not incorrectly rejected as foreign-owned, and no 500 crash)."""
        own_item = ItemInstanceFactory(holder_character_sheet=self.sheet)

        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:ritual-perform"),
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.ritual.pk,
                "kwargs": {"thread_id": self.thread.pk, "amount": 5},
                "components": [own_item.pk],
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)


class ThreadWeavingTeachingOfferViewSetTests(APITestCase):
    """Tests for GET /api/magic/teaching-offers/."""

    @classmethod
    def setUpTestData(cls) -> None:
        from world.relationships.factories import RelationshipTrackFactory

        cls.account = AccountFactory(username="offer_viewer")
        cls.trait_unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.TRAIT,
        )
        # Use RELATIONSHIP_TRACK so the target_kind filter meaningfully discriminates.
        cls.track_unlock = ThreadWeavingUnlockFactory(
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            unlock_trait=None,
            unlock_track=RelationshipTrackFactory(name="SanctifiedBond"),
        )
        cls.trait_offer = ThreadWeavingTeachingOfferFactory(unlock=cls.trait_unlock)
        cls.track_offer = ThreadWeavingTeachingOfferFactory(unlock=cls.track_unlock)

    def test_requires_auth(self) -> None:
        response = self.client.get(reverse("magic:thread-weaving-teaching-offer-list"))
        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_list_authenticated(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(reverse("magic:thread-weaving-teaching-offer-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 2)

    def test_filter_by_target_kind(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(
            reverse("magic:thread-weaving-teaching-offer-list"),
            {"target_kind": TargetKind.RELATIONSHIP_TRACK},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {o["id"] for o in response.data["results"]}
        self.assertIn(self.track_offer.pk, returned_ids)
        self.assertNotIn(self.trait_offer.pk, returned_ids)

    def test_list_is_read_only(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            reverse("magic:thread-weaving-teaching-offer-list"),
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class PermissionTests(APITestCase):
    """Direct checks on IsThreadOwner + retired filtering at the queryset layer."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner_account = AccountFactory(username="p_owner")
        cls.owner_character = CharacterFactory(db_key="POwner")
        cls.owner_sheet = CharacterSheetFactory(character=cls.owner_character)
        _link_account_to_sheet(cls.owner_account, cls.owner_character, cls.owner_sheet)

        cls.intruder_account = AccountFactory(username="p_intruder")
        cls.intruder_character = CharacterFactory(db_key="PIntruder")
        cls.intruder_sheet = CharacterSheetFactory(character=cls.intruder_character)
        _link_account_to_sheet(
            cls.intruder_account,
            cls.intruder_character,
            cls.intruder_sheet,
        )

        cls.staff_account = AccountFactory(username="p_staff", is_staff=True)

        cls.resonance = ResonanceFactory()
        cls.thread = ThreadFactory(
            owner=cls.owner_sheet,
            resonance=cls.resonance,
            target_trait=TraitFactory(),
        )

    def test_non_owner_cannot_retrieve(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.intruder_account)
        response = client.get(reverse("magic:thread-detail", args=[self.thread.pk]))
        # get_queryset filters by ownership → 404 before IsThreadOwner runs.
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_can_retrieve_any_thread(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff_account)
        response = client.get(reverse("magic:thread-detail", args=[self.thread.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_non_owner_cannot_soft_retire(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.intruder_account)
        response = client.delete(reverse("magic:thread-detail", args=[self.thread.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.thread.refresh_from_db()
        self.assertIsNone(self.thread.retired_at)


class RitualSerializerTests(APITestCase):
    """Tests for RitualSerializer."""

    @classmethod
    def setUpTestData(cls):
        cls.ritual = ImbuingRitualFactory(
            name="test_ritual",
            description="A ritual for testing.",
            input_schema={"fields": [{"name": "x", "type": "int", "label": "X"}]},
        )

    def test_serializer_includes_input_schema(self) -> None:
        from world.magic.serializers import RitualSerializer

        data = RitualSerializer(self.ritual).data
        self.assertIn("input_schema", data)
        self.assertEqual(data["input_schema"]["fields"][0]["name"], "x")

    def test_serializer_includes_dispatch_metadata(self) -> None:
        from world.magic.serializers import RitualSerializer

        data = RitualSerializer(self.ritual).data
        self.assertIn("execution_kind", data)
        self.assertIn("name", data)
        self.assertIn("description", data)
        self.assertIn("narrative_prose", data)
        self.assertIn("hedge_accessible", data)

    def test_is_imbuing_flags_the_imbuing_ritual_only(self) -> None:
        """The web Imbue flow resolves the ritual by this flag (2026-07 audit).

        The old frontend filtered on ``service_function_path`` — a field the
        serializer never sends — so web imbuing was unreachable everywhere.
        """
        from world.magic.factories import ImbuingRitualFactory, RitualFactory
        from world.magic.serializers import RitualSerializer

        # NOTE: this class's self.ritual is a RENAMED ImbuingRitualFactory row
        # ("test_ritual") — deliberately NOT the canonical rite, so it must not
        # flag. The canonical row (default name) must.
        canonical = ImbuingRitualFactory()
        self.assertTrue(RitualSerializer(canonical).data["is_imbuing"])
        self.assertFalse(RitualSerializer(self.ritual).data["is_imbuing"])
        other = RitualFactory(name="not_imbuing")
        self.assertFalse(RitualSerializer(other).data["is_imbuing"])


class RitualViewSetTests(APITestCase):
    """Tests for RitualViewSet (read-only)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = AccountFactory(username="ritual_vs_user")
        cls.ritual = RitualFactory(
            name="example_ritual",
            input_schema={"fields": [{"name": "x", "type": "int", "label": "X"}]},
        )

    def setUp(self):
        self.client.force_authenticate(self.user)

    def test_list_returns_rituals_with_input_schema(self):
        url = reverse("magic:ritual-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        names = [r["name"] for r in results]
        self.assertIn("example_ritual", names)
        # Find our specific ritual in the results
        target = next((r for r in results if r["name"] == "example_ritual"), None)
        self.assertIsNotNone(
            target,
            f"'example_ritual' not found in results: {[r['name'] for r in results]}",
        )
        self.assertEqual(target["input_schema"]["fields"][0]["name"], "x")

    def test_detail_returns_one_ritual(self):
        url = reverse("magic:ritual-detail", args=[self.ritual.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "example_ritual")

    def test_unauthenticated_request_rejected(self):
        self.client.force_authenticate(None)
        response = self.client.get(reverse("magic:ritual-list"))
        # Most DRF setups return 401 for unauthenticated; some configs return 403
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )


class TestRitualClientHosted(APITestCase):
    """Verify that Ritual.client_hosted is exposed by the list endpoint with correct values.

    Creates one generic ritual (client_hosted=False) and one Imbuing ritual
    (client_hosted=True), authenticates a player, and asserts both values are
    present and correct in the /api/magic/rituals/ response.
    """

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = AccountFactory(username="client_hosted_test_user")
        cls.generic_ritual = RitualFactory(name="generic_hosted_test_ritual")
        cls.imbuing_ritual = ImbuingRitualFactory()

    def setUp(self) -> None:
        self.client.force_authenticate(self.user)

    def test_client_hosted_false_on_generic_ritual(self) -> None:
        url = reverse("magic:ritual-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        target = next((r for r in results if r["name"] == "generic_hosted_test_ritual"), None)
        self.assertIsNotNone(
            target,
            f"'generic_hosted_test_ritual' not found in results: {[r['name'] for r in results]}",
        )
        self.assertIn("client_hosted", target)
        self.assertFalse(target["client_hosted"])

    def test_client_hosted_true_on_imbuing_ritual(self) -> None:
        url = reverse("magic:ritual-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        target = next((r for r in results if r["name"] == "Rite of Imbuing"), None)
        self.assertIsNotNone(
            target, f"'Rite of Imbuing' not found in results: {[r['name'] for r in results]}"
        )
        self.assertIn("client_hosted", target)
        self.assertTrue(target["client_hosted"])
