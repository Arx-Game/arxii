"""#761 + #881 — the renown fiction layer.

Qualitative ranking bands (the world never speaks raw numbers), the
perception fold into prestige ordering, the player rankings API, and the
room-entry fame reactions (actor/audience split, per-room/per-society
authoring, cooldown throttle).
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    ObjectDBFactory,
    RoomProfileFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.narrative.models import NarrativeMessageDelivery
from world.scenes.factories import PersonaFactory
from world.societies.constants import FameTier
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocietyFactory,
)
from world.societies.fame_reactions import maybe_emit_fame_reaction
from world.societies.models import (
    FameReactionCooldown,
    FameReactionLine,
    RankingBandLabel,
    RankingDisplay,
)
from world.societies.ranking_services import (
    _format_rows,
    band_labels_for,
    get_society_prestige_top_n,
)


def _society_member(society, *, name, prestige=0, fame_tier=FameTier.NORMAL):
    persona = PersonaFactory(name=name)
    persona.total_prestige = prestige
    persona.fame_points = 0
    persona.fame_tier = fame_tier
    persona.save(update_fields=["total_prestige", "fame_points", "fame_tier"])
    org = OrganizationFactory(name=f"{society.name} org", society=society)
    OrganizationMembershipFactory(persona=persona, organization=org)
    return persona


class QualitativeBandTests(TestCase):
    def setUp(self) -> None:
        self.society = SocietyFactory(name="Band Society")

    def test_scoped_bands_win_over_global(self) -> None:
        RankingBandLabel.objects.create(
            society=None, rank_min=1, rank_max=3, label="PLACEHOLDER globally known"
        )
        RankingBandLabel.objects.create(
            society=self.society, rank_min=1, rank_max=3, label="PLACEHOLDER court favorite"
        )
        labels = band_labels_for(self.society)
        self.assertEqual([b.label for b in labels], ["PLACEHOLDER court favorite"])

    def test_global_fallback_when_society_has_none(self) -> None:
        RankingBandLabel.objects.create(
            society=None, rank_min=1, rank_max=3, label="PLACEHOLDER globally known"
        )
        labels = band_labels_for(self.society)
        self.assertEqual([b.label for b in labels], ["PLACEHOLDER globally known"])

    def test_render_never_shows_numbers(self) -> None:
        RankingBandLabel.objects.create(
            society=self.society, rank_min=1, rank_max=1, label="PLACEHOLDER the foremost"
        )
        _society_member(self.society, name="Alice Numberless", prestige=12_345)
        rows = get_society_prestige_top_n(self.society, n=5)
        text = _format_rows(header="PLACEHOLDER header:", rows=rows)
        self.assertIn("Alice Numberless", text)
        self.assertIn("PLACEHOLDER the foremost", text)
        self.assertNotIn("12", text)  # no fragment of the raw value leaks

    def test_unauthored_bands_render_plain_names(self) -> None:
        _society_member(self.society, name="Plain Penny", prestige=10)
        rows = get_society_prestige_top_n(self.society, n=5)
        text = _format_rows(header="h:", rows=rows)
        self.assertIn("Plain Penny", text)
        self.assertNotIn("—", text)


class PerceptionFoldTests(TestCase):
    def test_fame_multiplier_reorders_ranking(self) -> None:
        society = SocietyFactory(name="Connected Society", fame_perception_offset=0)
        _society_member(society, name="Rich Roger", prestige=1_000, fame_tier=FameTier.NORMAL)
        _society_member(society, name="Famous Fiona", prestige=600, fame_tier=FameTier.CELEBRITY)
        rows = get_society_prestige_top_n(society, n=2)
        # 600 × 2.5 = 1500 beats 1000 × 1.0 — fame folds into the order.
        self.assertEqual(rows[0].persona_name, "Famous Fiona")

    def test_insular_society_hears_less(self) -> None:
        society = SocietyFactory(name="Insular Society", fame_perception_offset=-4)
        _society_member(society, name="Rich Roger", prestige=1_000, fame_tier=FameTier.NORMAL)
        _society_member(society, name="Famous Fiona", prestige=600, fame_tier=FameTier.CELEBRITY)
        rows = get_society_prestige_top_n(society, n=2)
        # Offset -4 floors Fiona's perceived tier to NORMAL: 600 < 1000.
        self.assertEqual(rows[0].persona_name, "Rich Roger")


class RankingApiTests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.account = AccountFactory(username="board-reader")
        self.client.force_authenticate(self.account)
        self.society = SocietyFactory(name="Gated Society")
        self.board_obj = ObjectDBFactory(db_key="herald")
        self.display = RankingDisplay.objects.create(
            display_object=self.board_obj,
            ranking_type=RankingDisplay.RankingType.SOCIETY_PRESTIGE,
            scope_society=self.society,
            top_n=5,
        )

    def test_non_member_gets_cloaked_board(self) -> None:
        with mock.patch("world.societies.ranking_views._viewer_persona", return_value=None):
            res = self.client.get(f"/api/societies/rankings/{self.display.pk}/")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["cloaked"])
        self.assertEqual(body["rows"], [])

    def test_member_sees_rows_without_numbers(self) -> None:
        member = _society_member(self.society, name="Seen Sela", prestige=500)
        with mock.patch("world.societies.ranking_views._viewer_persona", return_value=member):
            res = self.client.get(f"/api/societies/rankings/{self.display.pk}/")
        body = res.json()
        self.assertFalse(body["cloaked"])
        self.assertEqual(body["rows"][0]["persona_name"], "Seen Sela")
        self.assertNotIn("value", body["rows"][0])

    def test_unknown_display_is_404(self) -> None:
        res = self.client.get("/api/societies/rankings/999999/")
        self.assertEqual(res.status_code, 404)


def _room(name: str):
    room = ObjectDBFactory(db_key=name, db_typeclass_path="typeclasses.rooms.Room")
    profile = RoomProfileFactory(objectdb=room)
    return room, profile


def _arriver(room, *, fame_tier=FameTier.CELEBRITY):
    character = CharacterFactory()
    sheet = CharacterSheetFactory(character=character)
    persona = sheet.primary_persona
    persona.fame_tier = fame_tier
    persona.save(update_fields=["fame_tier"])
    character.db_location = room
    character.save(update_fields=["db_location"])
    return character, persona


def _bystander(room):
    character = CharacterFactory()
    CharacterSheetFactory(character=character)
    character.db_location = room
    character.save(update_fields=["db_location"])
    return character


class FameReactionTests(TestCase):
    def setUp(self) -> None:
        self.room, self.profile = _room("Grand Salon")

    def _line(self, **kwargs):
        defaults = {
            "room": self.profile,
            "min_fame_tier": FameTier.CELEBRITY,
            "bystander_body": "PLACEHOLDER heads turn as someone notable arrives.",
            "arriver_body": "PLACEHOLDER you feel the salon take notice.",
        }
        defaults.update(kwargs)
        return FameReactionLine.objects.create(**defaults)

    def test_actor_audience_split(self) -> None:
        self._line()
        arriver, _ = _arriver(self.room)
        bystander = _bystander(self.room)
        self.assertTrue(maybe_emit_fame_reaction(arriver, self.room))

        bystander_msgs = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=bystander.sheet_data
            ).values_list("message__body", flat=True)
        )
        arriver_msgs = list(
            NarrativeMessageDelivery.objects.filter(
                recipient_character_sheet=arriver.sheet_data
            ).values_list("message__body", flat=True)
        )
        self.assertEqual(bystander_msgs, ["PLACEHOLDER heads turn as someone notable arrives."])
        self.assertEqual(arriver_msgs, ["PLACEHOLDER you feel the salon take notice."])

    def test_below_threshold_is_silent(self) -> None:
        self._line()
        arriver, _ = _arriver(self.room, fame_tier=FameTier.NORMAL)
        self.assertFalse(maybe_emit_fame_reaction(arriver, self.room))

    def test_insular_society_voice_hears_less(self) -> None:
        insular = SocietyFactory(name="Insular Voice", fame_perception_offset=-2)
        self._line(society=insular)
        # CELEBRITY (index 2) - 2 = NORMAL < CELEBRITY threshold → silent.
        arriver, _ = _arriver(self.room, fame_tier=FameTier.CELEBRITY)
        self.assertFalse(maybe_emit_fame_reaction(arriver, self.room))
        # WORLD_FAMOUS (index 4) - 2 = CELEBRITY → fires.
        loud, _ = _arriver(self.room, fame_tier=FameTier.WORLD_FAMOUS)
        self.assertTrue(maybe_emit_fame_reaction(loud, self.room))

    def test_cooldown_blocks_refire(self) -> None:
        self._line()
        arriver, persona = _arriver(self.room)
        self.assertTrue(maybe_emit_fame_reaction(arriver, self.room))
        self.assertTrue(
            FameReactionCooldown.objects.filter(persona=persona, room=self.profile).exists()
        )
        self.assertFalse(maybe_emit_fame_reaction(arriver, self.room))

    def test_unauthored_room_is_silent(self) -> None:
        bare_room, _ = _room("Bare Hall")
        arriver, _ = _arriver(bare_room)
        self.assertFalse(maybe_emit_fame_reaction(arriver, bare_room))

    def test_sheetless_arriver_is_silent(self) -> None:
        self._line()
        sheetless = CharacterFactory()
        self.assertFalse(maybe_emit_fame_reaction(sheetless, self.room))
