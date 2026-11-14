"""The REST surface of a character with several resonances (#5123).

A thread lists every resonance it holds, the aura says whether the character is unsettled
in words, the pull preview lists each pulled thread's payers with their own perks, the
accept endpoint dispatches the action the telnet verb runs, an imbue names the resonance
that pays, and the character creation draft takes the weighted resonance picks.
"""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_creation.factories import CharacterDraftFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import TargetKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    GiftFactory,
    ImbuingRitualFactory,
    ResonanceFactory,
    ThreadFactory,
    ThreadPullCostFactory,
    ThreadPullEffectFactory,
    ThreadResonanceFactory,
    ensure_canonical_affinities,
    set_aura_split,
)
from world.magic.models import CharacterResonance, PendingRitualEffect, ThreadResonance
from world.magic.services.thread_rows import refresh_leading_resonance
from world.magic.specialization.services import provision_latent_gift_thread
from world.roster.factories import RosterTenureFactory
from world.traits.factories import TraitFactory


class _CharacterWithResonances(APITestCase):
    """A player's character holding Fury (Primal), Domination (Abyssal) and Wonder (Celestial)."""

    def setUp(self) -> None:
        super().setUp()
        self.celestial, self.primal, self.abyssal = ensure_canonical_affinities()
        self.fury = ResonanceFactory(name="Fury", affinity=self.primal)
        self.domination = ResonanceFactory(name="Domination", affinity=self.abyssal)
        self.wonder = ResonanceFactory(name="Wonder", affinity=self.celestial)
        self.account = AccountFactory()
        self.character = CharacterFactory(db_key="Several")
        self.sheet = CharacterSheetFactory(character=self.character)
        self.character.account = self.account
        self.account.characters.add(self.character)
        RosterTenureFactory(
            roster_entry__character_sheet=self.sheet, player_data__account=self.account
        )
        self.client.force_authenticate(user=self.account)

    def _hold(self, resonance, *, balance=0, lifetime=0, mire=0) -> CharacterResonance:
        return CharacterResonanceFactory(
            character_sheet=self.sheet,
            resonance=resonance,
            balance=balance,
            lifetime_earned=lifetime,
            mire_lifetime=mire,
        )

    def _primal_character_who_has_grown_abyssal(self, *, mire: int = 0) -> None:
        """Settled wholly Primal, with 30 of 100 lifetime resonance now Abyssal."""
        aura = CharacterAuraFactory(character=self.sheet)
        set_aura_split(aura, celestial="0", primal="100", abyssal="0")
        self._hold(self.fury, balance=70, lifetime=70)
        self._hold(self.domination, balance=30, lifetime=30, mire=mire)
        self.aura = aura

    def _aura_url(self, action: str = "") -> str:
        return f"/api/magic/character-auras/{self.aura.pk}/{action}"


class ThreadPayloadTests(_CharacterWithResonances):
    def test_thread_payload_lists_resonances(self) -> None:
        thread = ThreadFactory(
            owner=self.sheet, resonance=self.fury, target_trait=TraitFactory(), level=20
        )
        ThreadResonanceFactory(thread=thread, resonance=self.fury, amount=10)
        ThreadResonanceFactory(thread=thread, resonance=self.domination, amount=15)
        refresh_leading_resonance(thread)

        response = self.client.get(reverse("magic:thread-detail", args=[thread.pk]))

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        # The existing field is still the leading resonance.
        self.assertEqual(response.data["resonance"], self.domination.pk)
        self.assertEqual(response.data["resonance_name"], "Domination")
        self.assertEqual(
            [
                (row["resonance_id"], row["resonance_name"], row["amount"], row["leads"])
                for row in response.data["resonances"]
            ],
            [
                (self.domination.pk, "Domination", 15, True),
                (self.fury.pk, "Fury", 10, False),
            ],
        )


class AuraPayloadTests(_CharacterWithResonances):
    def test_aura_payload_unsettled_line(self) -> None:
        self._primal_character_who_has_grown_abyssal(mire=10)

        response = self.client.get(self._aura_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIs(response.data["unsettled"], True)
        self.assertEqual(
            response.data["unsettled_line"],
            "Your Domination has grown strong enough to make you unsettled.",
        )
        # Ten of a hundred lifetime points are the Mire's: said in words, never a number.
        self.assertEqual(response.data["mire_share_words"], "a tenth")
        shares = {row["affinity_name"]: row for row in response.data["shares"]}
        self.assertEqual(float(shares[self.primal.name]["settled_percent"]), 100.0)
        # No Abyssal share has been settled, so it has no row at all.
        self.assertNotIn(self.abyssal.name, shares)

    def test_aura_names_the_affinity_the_server_says_you_become_more(self) -> None:
        """Settled Celestial 60, Primal 30, Abyssal 10; now Celestial 70, Primal 10, Abyssal 20.

        Celestial grew most in raw terms, but only the Abyssal has passed what was settled
        plus the tolerance, so the aura names Abyssal, as accepting will.
        """
        aura = CharacterAuraFactory(character=self.sheet)
        set_aura_split(aura, celestial="60", primal="30", abyssal="10")
        self._hold(self.wonder, balance=70, lifetime=70)
        self._hold(self.fury, balance=10, lifetime=10)
        self._hold(self.domination, balance=20, lifetime=20)
        self.aura = aura

        response = self.client.get(self._aura_url())

        self.assertEqual(response.data["unsettled_affinity_name"], self.abyssal.name)
        done = self.client.post(self._aura_url("accept/"))
        self.assertEqual(done.data["detail"], "You become more abyssal.")
        self.assertEqual(done.data["aura"]["unsettled_affinity_name"], "")

    def test_each_aura_reads_its_resonances_once(self) -> None:
        self._primal_character_who_has_grown_abyssal(mire=10)
        table = CharacterResonance._meta.db_table
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self._aura_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        reads = sum(1 for q in queries.captured_queries if f'"{table}"' in q["sql"])
        self.assertEqual(reads, 1)

    def test_a_settled_aura_says_nothing_of_it(self) -> None:
        aura = CharacterAuraFactory(character=self.sheet)
        set_aura_split(aura, celestial="0", primal="100", abyssal="0")
        self._hold(self.fury, balance=100, lifetime=100)
        self.aura = aura

        response = self.client.get(self._aura_url())

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIs(response.data["unsettled"], False)
        self.assertEqual(response.data["unsettled_line"], "")
        self.assertEqual(response.data["mire_share_words"], "none")


class AcceptEndpointTests(_CharacterWithResonances):
    def test_accept_endpoint(self) -> None:
        self._primal_character_who_has_grown_abyssal()

        done = self.client.post(self._aura_url("accept/"))
        again = self.client.post(self._aura_url("accept/"))

        self.assertEqual(done.status_code, status.HTTP_200_OK, done.data)
        self.assertEqual(done.data["detail"], "You become more abyssal.")
        self.assertIs(done.data["aura"]["unsettled"], False)
        settled = {row["affinity_name"]: row for row in done.data["aura"]["shares"]}
        self.assertEqual(float(settled[self.abyssal.name]["settled_percent"]), 30.0)
        # Nothing left to accept: refused in the action's own words.
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("accepted", again.data["detail"])

    def test_nobody_accepts_for_another_players_character(self) -> None:
        self._primal_character_who_has_grown_abyssal()
        self.client.force_authenticate(user=AccountFactory())

        response = self.client.post(self._aura_url("accept/"))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            CharacterResonance.objects.get(
                character_sheet=self.sheet, resonance=self.domination
            ).mire_lifetime,
            0,
        )


class PreviewPayloadTests(_CharacterWithResonances):
    def test_preview_payload_per_payer_effects(self) -> None:
        trait = TraitFactory()
        thread = ThreadFactory(owner=self.sheet, resonance=self.fury, target_trait=trait, level=20)
        ThreadResonanceFactory(thread=thread, resonance=self.fury, amount=10)
        ThreadResonanceFactory(thread=thread, resonance=self.domination, amount=4)
        # The factories write rows behind the character's thread handler.
        self.character.threads.invalidate()
        ThreadPullCostFactory(tier=1, resonance_cost=3, anima_per_thread=2)
        CharacterAnimaFactory(character=self.sheet, current=10, maximum=10)
        self._hold(self.fury, balance=10, lifetime=10)
        self._hold(self.domination, balance=5, lifetime=5)
        # Held, but the thread has no row for it.
        self._hold(self.wonder, balance=0, lifetime=0)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT, resonance=self.fury, tier=0, flat_bonus_amount=2
        )
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT, resonance=self.domination, tier=1, flat_bonus_amount=5
        )

        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {"character_sheet_id": self.sheet.pk, "tier": 1, "thread_ids": [thread.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        (pulled,) = response.data["per_thread"]
        self.assertEqual(pulled["thread_id"], thread.pk)
        options = {row["resonance_name"]: row for row in pulled["options"]}
        self.assertEqual(set(options), {"Fury", "Domination", "Wonder"})
        # Each payer carries its own perks; none is summed into another's. A resonance that
        # does not lead the thread has no tier-0 passive, so its perk is the tier-1 row.
        self.assertEqual([e["authored_value"] for e in options["Fury"]["effects"]], [2])
        self.assertEqual([e["authored_value"] for e in options["Domination"]["effects"]], [5])
        self.assertEqual(options["Wonder"]["effects"], [])
        self.assertEqual(
            {
                name: (row["cost"], row["balance"], row["affordable"])
                for name, row in options.items()
            },
            {"Fury": (3, 10, True), "Domination": (3, 5, True), "Wonder": (3, 0, False)},
        )
        self.assertIn("level_read", options["Fury"])

    def test_preview_perk_names_the_capability_it_grants(self) -> None:
        """A capability perk row carries the capability's name and its magnitude."""
        trait = TraitFactory()
        thread = ThreadFactory(owner=self.sheet, resonance=self.fury, target_trait=trait, level=20)
        ThreadResonanceFactory(thread=thread, resonance=self.fury, amount=10)
        self.character.threads.invalidate()
        ThreadPullCostFactory(tier=1, resonance_cost=3, anima_per_thread=2)
        CharacterAnimaFactory(character=self.sheet, current=10, maximum=10)
        self._hold(self.fury, balance=10, lifetime=10)
        ThreadPullEffectFactory(
            target_kind=TargetKind.TRAIT,
            resonance=self.fury,
            tier=1,
            as_capability_grant=True,
            capability_grant__name="Cowed",
            capability_grant_value=2,
        )

        response = self.client.post(
            reverse("magic:thread-pull-preview"),
            {"character_sheet_id": self.sheet.pk, "tier": 1, "thread_ids": [thread.pk]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        (pulled,) = response.data["per_thread"]
        (fury,) = [row for row in pulled["options"] if row["resonance_name"] == "Fury"]
        (perk,) = fury["effects"]
        self.assertEqual(perk["kind"], "CAPABILITY_GRANT")
        self.assertEqual(perk["capability_name"], "Cowed")
        # No capability power curve is authored here, so the authored base stands.
        self.assertEqual(perk["capability_value"], 2)
        self.assertIsNone(perk["resistance_damage_type_name"])

    def _resonance_row_queries(self, thread_count: int) -> int:
        for _ in range(thread_count):
            thread = ThreadFactory(
                owner=self.sheet, resonance=self.fury, target_trait=TraitFactory(), level=2
            )
            ThreadResonanceFactory(thread=thread, resonance=self.fury, amount=10)
            ThreadResonanceFactory(thread=thread, resonance=self.domination, amount=15)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("magic:thread-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        table = ThreadResonance._meta.db_table
        return sum(1 for q in queries.captured_queries if f'"{table}"' in q["sql"])

    def test_thread_list_reads_the_resonance_rows_in_one_query(self) -> None:
        self.assertEqual(self._resonance_row_queries(1), 1)
        self.assertEqual(self._resonance_row_queries(4), 1)

    def test_thread_list_carries_each_threads_rows_and_allowed_set(self) -> None:
        gift = GiftFactory()
        gift.resonances.add(self.fury, self.wonder)
        gift_thread = provision_latent_gift_thread(self.sheet, gift, resonances=[self.fury])
        plain = ThreadFactory(owner=self.sheet, resonance=self.fury, target_trait=TraitFactory())

        response = self.client.get(reverse("magic:thread-list"))

        by_id = {row["id"]: row for row in response.data["results"]}
        self.assertEqual(
            by_id[gift_thread.pk]["allowed_resonance_ids"],
            sorted([self.fury.pk, self.wonder.pk]),
        )
        self.assertIsNone(by_id[plain.pk]["allowed_resonance_ids"])
        self.assertEqual(
            [row["resonance_id"] for row in by_id[gift_thread.pk]["resonances"]],
            [self.fury.pk],
        )


class ImbuePayerTests(_CharacterWithResonances):
    def _imbue(self, **kwargs):
        return self.client.post(
            reverse("magic:ritual-perform"),
            {
                "character_sheet_id": self.sheet.pk,
                "ritual_id": self.ritual.pk,
                "kwargs": kwargs,
                "components": [],
            },
            format="json",
        )

    def setUp(self) -> None:
        super().setUp()
        self.ritual = ImbuingRitualFactory()
        CharacterAuraFactory(character=self.sheet)  # Gifted: the hedge gate
        self.thread = ThreadFactory(
            owner=self.sheet,
            resonance=self.fury,
            target_trait=TraitFactory(),
            level=2,
            _trait_value=9,
        )
        self._hold(self.fury, balance=20, lifetime=20)
        self._hold(self.domination, balance=20, lifetime=20)

    def test_imbue_endpoint_takes_resonance(self) -> None:
        response = self._imbue(thread_id=self.thread.pk, amount=5, resonance_id=self.domination.pk)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(
            CharacterResonance.objects.get(
                character_sheet=self.sheet, resonance=self.domination
            ).balance,
            15,
        )
        self.assertEqual(
            CharacterResonance.objects.get(character_sheet=self.sheet, resonance=self.fury).balance,
            20,
        )
        self.assertEqual(
            ThreadResonance.objects.get(thread=self.thread, resonance=self.domination).amount, 5
        )

    def test_imbue_refuses_a_resonance_the_character_does_not_hold(self) -> None:
        response = self._imbue(thread_id=self.thread.pk, amount=5, resonance_id=self.wonder.pk)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("resonance_id", response.data)
        self.assertFalse(PendingRitualEffect.objects.filter(character=self.sheet).exists())

    def test_imbue_refuses_a_resonance_a_restricted_gift_does_not_support(self) -> None:
        gift = GiftFactory()
        gift.resonances.add(self.fury, self.wonder)
        gift_thread = provision_latent_gift_thread(self.sheet, gift, resonances=[self.fury])

        response = self._imbue(thread_id=gift_thread.pk, amount=5, resonance_id=self.domination.pk)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertFalse(
            ThreadResonance.objects.filter(thread=gift_thread, resonance=self.domination).exists()
        )
        self.assertEqual(
            CharacterResonance.objects.get(
                character_sheet=self.sheet, resonance=self.domination
            ).balance,
            20,
        )


class DraftWeightsTests(APITestCase):
    def test_cg_draft_takes_weighted_resonance_picks(self) -> None:
        _celestial, primal, abyssal = ensure_canonical_affinities()
        fury = ResonanceFactory(name="Fury", affinity=primal)
        domination = ResonanceFactory(name="Domination", affinity=abyssal)
        account = AccountFactory()
        draft = CharacterDraftFactory(account=account, draft_data={})
        self.client.force_authenticate(user=account)
        url = f"/api/character-creation/drafts/{draft.pk}/"

        def save(weights):
            return self.client.patch(
                url, {"draft_data": {"gift_resonance_weights": weights}}, format="json"
            )

        # A spread still being worked through is saved and handed back as it was sent.
        partial = [
            {"resonance_id": fury.pk, "weight": 6},
            {"resonance_id": domination.pk, "weight": 1},
        ]
        saved = save(partial)
        self.assertEqual(saved.status_code, status.HTTP_200_OK, saved.data)
        self.assertEqual(saved.data["draft_data"]["gift_resonance_weights"], partial)

        # The stage's own refusals, in its own words, before the draft is changed.
        twice = save(
            [{"resonance_id": fury.pk, "weight": 3}, {"resonance_id": fury.pk, "weight": 3}]
        )
        self.assertEqual(twice.status_code, status.HTTP_400_BAD_REQUEST)
        over = save([{"resonance_id": fury.pk, "weight": 11}])
        self.assertEqual(over.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Spread exactly 10 points", str(over.data))
        draft.refresh_from_db()
        self.assertEqual(draft.draft_data["gift_resonance_weights"], partial)
