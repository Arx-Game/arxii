"""Tie API (#3957): per-audience reads, the seven writes, the stream, the catalogue."""

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.action_points.models import ActionPointPool
from world.character_sheets.factories import CharacterSheetFactory
from world.companions.factories import CompanionFactory
from world.journals.factories import JournalEntryFactory
from world.magic.constants import TargetKind
from world.magic.factories import ResonanceFactory
from world.magic.models import Thread
from world.relationships.constants import LabelAwareness, TypeFamily, TypeValence
from world.relationships.factories import RelationshipTierFactory, RelationshipTypeFactory
from world.relationships.models import RelationshipAllocation, RelationshipLabel
from world.relationships.services import (
    advance_awareness,
    declare_label,
    get_or_create_side,
    shift_label,
)
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.roster.services.selection import set_selected_entry


def _owned_sheet(account):
    """A sheet with a roster entry + current tenure the account owns, and selected.

    ``CharacterSheetFactory`` alone builds no ``RosterEntry`` (``sheet.roster_entry``
    would raise), so one is built explicitly here and the sheet's ObjectDB is given the
    account (``_resolve_actor`` checks ``sheet.character.db_account_id``); mirrors
    ``world.companions.tests.test_views._actor_user``.
    """
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(player_data__account=account, roster_entry=entry)
    sheet.character.db_account = account
    sheet.character.save(update_fields=["db_account"])
    set_selected_entry(tenure.player_data, entry)
    return sheet, tenure


class TieApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = AccountFactory()
        cls.other = AccountFactory()
        cls.stranger = AccountFactory()
        cls.staff = AccountFactory(is_staff=True)
        cls.a, cls.tenure_a = _owned_sheet(cls.owner)
        cls.b, cls.tenure_b = _owned_sheet(cls.other)
        cls.c, _ = _owned_sheet(cls.stranger)
        cls.lover = RelationshipTypeFactory(
            name="Lover", valence=TypeValence.WARM, family=TypeFamily.HEART
        )
        cls.enemy = RelationshipTypeFactory(
            name="Enemy", valence=TypeValence.HOSTILE, family=TypeFamily.CONTEST
        )
        cls.rival = RelationshipTypeFactory(
            name="Rival", valence=TypeValence.HOSTILE, family=TypeFamily.CONTEST
        )
        RelationshipTierFactory(tier_number=1, depth_threshold=25)
        RelationshipTierFactory(tier_number=2, depth_threshold=100)
        RelationshipTierFactory(tier_number=3, depth_threshold=500)
        cls.ab = get_or_create_side(source=cls.a, target=cls.b)
        cls.ab.scene_depth, cls.ab.invested_depth, cls.ab.tier = 48, 184, 2
        cls.ab.affection, cls.ab.conflict, cls.ab.summary = 41, 28, "A throat."
        cls.ab.save()
        cls.ba = get_or_create_side(source=cls.b, target=cls.a)
        cls.ba.scene_depth, cls.ba.invested_depth = 48, 60
        cls.ba.save()
        declare_label(
            side=cls.ab, type=cls.lover, awareness=LabelAwareness.CLANDESTINE, tenure=cls.tenure_a
        )
        declare_label(side=cls.ab, type=cls.enemy, tenure=cls.tenure_a)
        # A staff account that also PLAYS someone, so "staff reading a foreign tie" and
        # "staff reading their own" are two distinguishable cases (#3957 review C2).
        cls.s, cls.tenure_s = _owned_sheet(cls.staff)
        cls.sa = get_or_create_side(source=cls.s, target=cls.a)
        declare_label(side=cls.sa, type=cls.rival, tenure=cls.tenure_s)

    def _client(self, account):
        client = APIClient()
        client.force_authenticate(user=account)
        return client

    def test_owner_sees_everything(self):
        data = self._client(self.owner).get(f"/api/relationships/relationships/{self.ab.pk}/").data
        self.assertEqual(data["audience"], "owner")
        self.assertEqual(data["depth"], 340)
        self.assertEqual(data["next_tier_threshold"], 500)
        self.assertEqual([lab["type_name"] for lab in data["labels"]], ["Lover", "Enemy"])
        self.assertEqual(data["breakdown"]["affection"], 41)
        self.assertEqual(data["breakdown"]["their_added_depth"], 108)
        self.assertEqual(data["summary"], "A throat.")

    def test_other_side_sees_known_labels_and_no_feeling(self):
        data = self._client(self.other).get(f"/api/relationships/relationships/{self.ab.pk}/").data
        self.assertEqual(data["audience"], "other_side")
        self.assertEqual([lab["type_name"] for lab in data["labels"]], ["Lover"])
        self.assertEqual(data["depth"], 340)
        self.assertIsNone(data["breakdown"]["affection"])
        self.assertNotIn("ap_this_week", {k: v for k, v in data.items() if v is not None})

    def test_third_party_404s_without_a_public_label(self):
        url = f"/api/relationships/relationships/{self.ab.pk}/"
        response = self._client(self.stranger).get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_third_party_sees_public_labels_and_no_numbers(self):
        label = RelationshipLabel.objects.get(relationship=self.ab, type=self.lover)
        label.awareness = LabelAwareness.PUBLIC
        label.save(update_fields=["awareness"])
        url = f"/api/relationships/relationships/{self.ab.pk}/"
        data = self._client(self.stranger).get(url).data
        self.assertEqual(data["audience"], "third_party")
        self.assertEqual([lab["type_name"] for lab in data["labels"]], ["Lover"])
        self.assertIsNone(data["depth"])
        self.assertIsNone(data["breakdown"])
        self.assertEqual(data["summary"], "A throat.")

    def test_staff_sees_all(self):
        data = self._client(self.staff).get(f"/api/relationships/relationships/{self.ab.pk}/").data
        self.assertEqual(data["audience"], "staff")
        self.assertEqual(len(data["labels"]), 2)

    def test_is_own_side_true_only_for_the_side_the_viewer_plays(self):
        """The one flag the web client gates a write door on (#3957 review C2).

        ``audience`` cannot serve: ``tie_audience`` short-circuits on ``is_staff``, so a
        staff account reading ANY tie gets STAFF. Four of the seven writes resolve their
        side as ``get_or_create(source=the caller's own sheet, ...)``, so a door offered on
        that basis would have written a durable row on the staff character's own side.
        """
        url = f"/api/relationships/relationships/{self.ab.pk}/"
        self.assertTrue(self._client(self.owner).get(url).data["is_own_side"])

    def test_is_own_side_false_for_the_other_party(self):
        url = f"/api/relationships/relationships/{self.ab.pk}/"
        data = self._client(self.other).get(url).data
        self.assertEqual(data["audience"], "other_side")
        self.assertFalse(data["is_own_side"])

    def test_is_own_side_false_for_a_third_party(self):
        label = RelationshipLabel.objects.get(relationship=self.ab, type=self.lover)
        label.awareness = LabelAwareness.PUBLIC
        label.save(update_fields=["awareness"])
        url = f"/api/relationships/relationships/{self.ab.pk}/"
        data = self._client(self.stranger).get(url).data
        self.assertEqual(data["audience"], "third_party")
        self.assertFalse(data["is_own_side"])

    def test_is_own_side_false_for_staff_on_someone_elses_tie(self):
        url = f"/api/relationships/relationships/{self.ab.pk}/"
        data = self._client(self.staff).get(url).data
        self.assertEqual(data["audience"], "staff")
        self.assertFalse(data["is_own_side"])

    def test_is_own_side_true_for_staff_on_their_own_tie(self):
        url = f"/api/relationships/relationships/{self.sa.pk}/"
        data = self._client(self.staff).get(url).data
        self.assertEqual(data["audience"], "staff")
        self.assertTrue(data["is_own_side"])

    def test_list_rows_are_all_own_sides(self):
        data = self._client(self.owner).get("/api/relationships/relationships/").data
        self.assertTrue(all(row["is_own_side"] for row in data["results"]))

    def test_list_is_own_sides_only(self):
        data = self._client(self.owner).get("/api/relationships/relationships/").data
        ids = [row["id"] for row in data["results"]]
        self.assertEqual(ids, [self.ab.pk])

    def test_writes(self):
        client = self._client(self.other)
        response = client.post(
            "/api/relationships/relationships/declare/",
            {
                "target_persona_id": self.a.personas.first().pk,
                "type_id": self.rival.pk,
                "awareness": "public",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        label_id = response.data["data"]["label_id"]
        response = client.post(
            "/api/relationships/relationships/awareness/",
            {"label_id": label_id, "awareness": "private"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = client.post(
            "/api/relationships/relationships/shift/",
            {"label_id": label_id, "new_type_id": self.enemy.pk, "note": "worse"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        response = client.post(
            "/api/relationships/relationships/summary/",
            {"target_persona_id": self.a.personas.first().pk, "summary": "Hers."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        response = client.post(
            "/api/relationships/relationships/end/",
            {"label_id": response.data["data"].get("label_id", label_id)},
            format="json",
        )
        self.assertIn(response.status_code, (status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST))

    def test_label_write_refused_for_someone_elses_label(self):
        label = RelationshipLabel.objects.get(relationship=self.ab, type=self.lover)
        response = self._client(self.other).post(
            "/api/relationships/relationships/end/", {"label_id": label.pk}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["message"], "That is not your relationship.")

    def test_stream_filters_by_viewer(self):
        JournalEntryFactory(author=self.a, about=self.b, is_public=False, title="Black")
        JournalEntryFactory(author=self.b, about=self.a, is_public=True, title="White")
        url = f"/api/relationships/relationships/{self.ab.pk}/stream/"
        data = self._client(self.other).get(url).data
        self.assertEqual([i["title"] for i in data], ["White"])

    def test_types_catalogue(self):
        data = self._client(self.stranger).get("/api/relationships/types/").data
        names = {row["name"] for row in data.get("results", data)}
        self.assertEqual(names, {"Lover", "Enemy", "Rival"})

    def test_ap_this_week_visible_to_owner_and_staff_only(self):
        RelationshipAllocation.objects.create(relationship=self.ab, ap_amount=7)
        url = f"/api/relationships/relationships/{self.ab.pk}/"
        owner_data = self._client(self.owner).get(url).data
        self.assertEqual(owner_data["ap_this_week"], 7)
        other_data = self._client(self.other).get(url).data
        self.assertIsNone(other_data["ap_this_week"])
        staff_data = self._client(self.staff).get(url).data
        self.assertEqual(staff_data["ap_this_week"], 7)
        label = RelationshipLabel.objects.get(relationship=self.ab, type=self.lover)
        label.awareness = LabelAwareness.PUBLIC
        label.save(update_fields=["awareness"])
        stranger_data = self._client(self.stranger).get(url).data
        self.assertIsNone(stranger_data["ap_this_week"])

    def test_ap_pool_is_the_owners_own_and_nobody_elses(self):
        """The budget line beside the AP field (#3957): remaining over the week's total.

        Gated on the side being the viewer's OWN, not on audience — so the other party
        gets null, and so does a staff account, whose own purse this is not.
        """
        pool = ActionPointPool.get_or_create_for_character(self.a.character)
        pool.maximum, pool.current = 40, 31
        pool.save(update_fields=["maximum", "current"])
        url = f"/api/relationships/relationships/{self.ab.pk}/"

        owner_data = self._client(self.owner).get(url).data
        self.assertEqual(owner_data["ap_pool"], {"remaining": 31, "total": 40})

        self.assertIsNone(self._client(self.other).get(url).data["ap_pool"])
        self.assertIsNone(self._client(self.staff).get(url).data["ap_pool"])

        label = RelationshipLabel.objects.get(relationship=self.ab, type=self.lover)
        label.awareness = LabelAwareness.PUBLIC
        label.save(update_fields=["awareness"])
        self.assertIsNone(self._client(self.stranger).get(url).data["ap_pool"])

    def test_ap_pool_is_null_when_the_owner_has_no_pool_row(self):
        """No pool row is a data state, not a reason to refuse the page."""
        ActionPointPool.objects.filter(character=self.a).delete()
        data = self._client(self.owner).get(f"/api/relationships/relationships/{self.ab.pk}/").data
        self.assertIsNone(data["ap_pool"])

    def test_breakdown_conflict_null_for_other_side(self):
        data = self._client(self.other).get(f"/api/relationships/relationships/{self.ab.pk}/").data
        self.assertIsNone(data["breakdown"]["conflict"])

    def test_third_party_never_sees_thread_or_a_hidden_replaced_label(self):
        Thread.objects.create(
            owner=self.a,
            resonance=ResonanceFactory(),
            target_kind=TargetKind.RELATIONSHIP_TRACK,
            target_relationship=self.ab,
            level=20,
        )
        secret_type = RelationshipTypeFactory(name="Secret")
        known_type = RelationshipTypeFactory(name="Known")
        private_label = declare_label(
            side=self.ab, type=secret_type, awareness=LabelAwareness.PRIVATE
        )
        shifted = shift_label(label=private_label, new_type=known_type)
        advance_awareness(label=shifted, to=LabelAwareness.PUBLIC)

        owner_data = (
            self._client(self.owner).get(f"/api/relationships/relationships/{self.ab.pk}/").data
        )
        self.assertIsNotNone(owner_data["thread"])
        owner_known = next(lab for lab in owner_data["labels"] if lab["type_name"] == "Known")
        self.assertEqual(owner_known["replaced_type_name"], "Secret")

        stranger_data = (
            self._client(self.stranger).get(f"/api/relationships/relationships/{self.ab.pk}/").data
        )
        self.assertIsNone(stranger_data["thread"])
        stranger_known = next(lab for lab in stranger_data["labels"] if lab["type_name"] == "Known")
        self.assertIsNone(stranger_known["replaced_type_name"])

    def test_third_party_mutual_needs_both_sides_public(self):
        mutual_type = RelationshipTypeFactory(name="Ally")
        declare_label(
            side=self.ab, type=mutual_type, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_a
        )
        declare_label(
            side=self.ba,
            type=mutual_type,
            awareness=LabelAwareness.CLANDESTINE,
            tenure=self.tenure_b,
        )
        url = f"/api/relationships/relationships/{self.ab.pk}/"

        data = self._client(self.stranger).get(url).data
        row = next(lab for lab in data["labels"] if lab["type_name"] == "Ally")
        self.assertFalse(row["is_mutual"])

        ba_label = RelationshipLabel.objects.get(relationship=self.ba, type=mutual_type)
        ba_label.awareness = LabelAwareness.PUBLIC
        ba_label.save(update_fields=["awareness"])
        data = self._client(self.stranger).get(url).data
        row = next(lab for lab in data["labels"] if lab["type_name"] == "Ally")
        self.assertTrue(row["is_mutual"])

    def test_mutual_needs_an_open_tenure_on_both_labels(self):
        mutual_type = RelationshipTypeFactory(name="Confidant")
        declare_label(
            side=self.ab, type=mutual_type, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_a
        )
        closed_tenure = RosterTenureFactory(roster_entry=self.b.roster_entry)
        closed_tenure.end_date = closed_tenure.start_date
        closed_tenure.save(update_fields=["end_date"])
        declare_label(
            side=self.ba, type=mutual_type, awareness=LabelAwareness.PUBLIC, tenure=closed_tenure
        )
        data = (
            self._client(self.stranger).get(f"/api/relationships/relationships/{self.ab.pk}/").data
        )
        row = next(lab for lab in data["labels"] if lab["type_name"] == "Confidant")
        self.assertFalse(row["is_mutual"])

    def test_mutual_needs_an_active_reverse_side(self):
        mutual_type = RelationshipTypeFactory(name="Bonded")
        declare_label(
            side=self.ab, type=mutual_type, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_a
        )
        declare_label(
            side=self.ba, type=mutual_type, awareness=LabelAwareness.PUBLIC, tenure=self.tenure_b
        )
        self.ba.is_active = False
        self.ba.save(update_fields=["is_active"])
        url = f"/api/relationships/relationships/{self.ab.pk}/"
        data = self._client(self.stranger).get(url).data
        row = next(lab for lab in data["labels"] if lab["type_name"] == "Bonded")
        self.assertFalse(row["is_mutual"])

        # A frozen reverse side stops EARNING but keeps the depth it already earned (spec
        # Decision 2): the owner still sees the full pair_depth(), including ba's frozen
        # contribution, even though mutuality (above) correctly stays false regardless.
        owner_data = self._client(self.owner).get(url).data
        self.assertEqual(owner_data["depth"], 340)
        self.assertEqual(owner_data["breakdown"]["their_added_depth"], 108)

    def test_companion_side_404s_for_anyone_but_owner_or_staff(self):
        companion = CompanionFactory(owner=self.a)
        companion_side = get_or_create_side(source=self.a, target_companion=companion)
        declare_label(side=companion_side, type=self.lover, awareness=LabelAwareness.PUBLIC)
        retrieve_url = f"/api/relationships/relationships/{companion_side.pk}/"
        stream_url = f"/api/relationships/relationships/{companion_side.pk}/stream/"

        self.assertEqual(self._client(self.owner).get(retrieve_url).status_code, status.HTTP_200_OK)
        self.assertEqual(self._client(self.staff).get(retrieve_url).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self._client(self.stranger).get(retrieve_url).status_code, status.HTTP_404_NOT_FOUND
        )
        self.assertEqual(self._client(self.owner).get(stream_url).status_code, status.HTTP_200_OK)
        self.assertEqual(
            self._client(self.stranger).get(stream_url).status_code, status.HTTP_404_NOT_FOUND
        )

    def test_declare_validation_failure_returns_the_honest_shape(self):
        response = self._client(self.owner).post(
            "/api/relationships/relationships/declare/",
            {"type_id": self.lover.pk, "awareness": "public"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data["success"])
        self.assertIn("message", response.data)
        self.assertIn("data", response.data)

    def test_list_query_budget_stays_flat_across_a_page(self):
        """``build_tie_page`` adds a small, page-size-independent query count (#3957 review):
        15 queries for a 6-row page here (session + count + queryset + labels prefetch +
        reverse sides + reverse labels prefetch + threads + tier ladder + the owners' AP
        pools, plus session-save bookkeeping) — not one per row.

        The AP-pool lookup is the fifteenth and is batched over the page's distinct
        OWNERS, so it is asserted by count rather than left to the ceiling: a per-row
        ``side.source.action_points`` would pass the ceiling on a small page and fail on
        a full one.
        """
        for i in range(5):
            target, _ = _owned_sheet(AccountFactory())
            side = get_or_create_side(source=self.a, target=target)
            side.scene_depth = 10 * i
            side.save()
            declare_label(side=side, type=self.lover, awareness=LabelAwareness.PUBLIC)
        with CaptureQueriesContext(connection) as ctx:
            response = self._client(self.owner).get("/api/relationships/relationships/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 6)
        pool_table = ActionPointPool._meta.db_table
        pool_queries = [q for q in ctx.captured_queries if pool_table in q["sql"]]
        self.assertEqual(len(pool_queries), 1)
        self.assertLessEqual(len(ctx.captured_queries), 15)

    def test_list_matches_reverse_depth_per_target_when_two_owned_characters_share_one(self):
        """Two characters under one account, each with a side toward the SAME target: the
        reverse-side map must key on the (source, target) PAIR, not the target alone — both
        reverse rows share a source_id (the shared target), so a source-only key collides and
        hands one row the other's depth (#3957 review).
        """
        player_data, _ = PlayerData.objects.get_or_create(account=self.owner)
        second_owned = CharacterSheetFactory()
        second_entry = RosterEntryFactory(character_sheet=second_owned)
        RosterTenureFactory(player_data=player_data, roster_entry=second_entry)

        side_a_to_c = get_or_create_side(source=self.a, target=self.c)
        side_a_to_c.scene_depth = 10
        side_a_to_c.save()
        side_second_to_c = get_or_create_side(source=second_owned, target=self.c)
        side_second_to_c.scene_depth = 20
        side_second_to_c.save()
        reverse_c_to_a = get_or_create_side(source=self.c, target=self.a)
        reverse_c_to_a.scene_depth = 100
        reverse_c_to_a.save()
        reverse_c_to_second = get_or_create_side(source=self.c, target=second_owned)
        reverse_c_to_second.scene_depth = 200
        reverse_c_to_second.save()

        data = self._client(self.owner).get("/api/relationships/relationships/").data
        rows = {row["id"]: row for row in data["results"]}
        row_a = rows[side_a_to_c.pk]
        row_second = rows[side_second_to_c.pk]
        self.assertEqual(row_a["depth"], 10 + 100)
        self.assertEqual(row_a["breakdown"]["their_added_depth"], 100)
        self.assertEqual(row_second["depth"], 20 + 200)
        self.assertEqual(row_second["breakdown"]["their_added_depth"], 200)
