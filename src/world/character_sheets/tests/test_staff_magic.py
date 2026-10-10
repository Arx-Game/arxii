"""Staff edit mode, piece C: Grant magic on a giftless sheet, and a versioned Glimpse (#4224)."""

from __future__ import annotations

from types import SimpleNamespace

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from rest_framework.test import APIClient

from actions.factories import ActionTemplateFactory
from evennia_extensions.factories import AccountFactory
from world.character_sheets.models import ProfileTextVersion
from world.character_sheets.services import ensure_true_profile
from world.magic.admin import CharacterAuraAdmin
from world.magic.constants import AcquisitionOrigin, GlimpseState
from world.magic.factories import (
    CharacterAuraFactory,
    GiftFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TraditionFactory,
    TraditionGiftGrantFactory,
)
from world.magic.models import (
    CharacterAura,
    CharacterGift,
    CharacterTechnique,
    CharacterTradition,
)
from world.magic.models.ritual_check_config import RitualCheckConfig
from world.magic.services.glimpse import set_glimpse_prose
from world.progression.factories import CharacterPathHistoryFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.skills.factories import SkillFactory
from world.traits.factories import StatTraitFactory


class GrantMagicTests(TestCase):
    """POST staff-magic gives a giftless sheet what CG's magic stage would have."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)
        cls.player = PlayerDataFactory()
        cls.tradition = TraditionFactory(name="Staff Grant Tradition")
        cls.resonance = ResonanceFactory()
        cls.gift = GiftFactory(name="Staff Grant Gift")
        cls.gift.resonances.add(cls.resonance)
        cls.finished = TechniqueFactory(
            gift=cls.gift, name="Finished Step", action_template=ActionTemplateFactory()
        )
        cls.unfinished = TechniqueFactory(gift=cls.gift, name="Unfinished Step")
        cls.second = TechniqueFactory(
            gift=cls.gift, name="Second Step", action_template=ActionTemplateFactory()
        )
        cls.stray = TechniqueFactory(name="Stray Step", action_template=ActionTemplateFactory())
        grant = TraditionGiftGrantFactory(tradition=cls.tradition, gift=cls.gift)
        grant.special_techniques.add(cls.finished, cls.unfinished, cls.second)
        cls.stat = StatTraitFactory(name="staff_grant_focus")
        cls.skill = SkillFactory()

    def setUp(self) -> None:
        self.entry = RosterEntryFactory()
        RosterTenureFactory(player_data=self.player, roster_entry=self.entry, player_number=1)
        self.sheet = self.entry.character_sheet
        self.path_row = CharacterPathHistoryFactory(character=self.sheet)
        PathGiftGrantFactory(path=self.path_row.path, gift=self.gift)
        self.base = f"/api/character-sheets/{self.sheet.pk}"
        self.client = APIClient()
        self.client.force_authenticate(user=self.staff)

    def _payload(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "tradition": self.tradition.pk,
            "gift": self.gift.pk,
            "techniques": [self.finished.pk],
            "resonance": self.resonance.pk,
            "anima_stat": self.stat.pk,
            "anima_skill": self.skill.pk,
            "ritual_name": "Dawn Vigil",
            "glimpse": "The lamp went out and I could still see.",
        }
        payload.update(overrides)
        return payload

    def test_grant_writes_the_rows_cg_would(self) -> None:
        response = self.client.post(f"{self.base}/staff-magic/", self._payload(), format="json")
        assert response.status_code == 200, response.content[:800]
        rows = response.data["staff_edit"]["rows"]
        assert (rows["has_gift"], rows["has_aura"]) == (True, True)
        gift = CharacterGift.objects.get(character=self.sheet)
        assert gift.gift == self.gift
        assert gift.origin == AcquisitionOrigin.CHARACTER_CREATION
        assert set(
            CharacterTechnique.objects.filter(character=self.sheet).values_list(
                "technique_id", flat=True
            )
        ) == {self.finished.pk}
        assert CharacterTradition.objects.filter(
            character=self.sheet, tradition=self.tradition
        ).exists()
        aura = CharacterAura.objects.get(character=self.sheet)
        assert aura.glimpse_story == "The lamp went out and I could still see."
        config = RitualCheckConfig.objects.get(ritual__name="Dawn Vigil")
        assert (config.stat, config.skill, config.resonance) == (
            self.stat,
            self.skill,
            self.resonance,
        )
        # The ritual belongs to the player, never the staff member who granted it.
        assert config.ritual.author_account == self.player.account

    def test_the_glimpse_versions_with_the_other_prose(self) -> None:
        self.client.post(f"{self.base}/staff-magic/", self._payload(), format="json")
        profile = ensure_true_profile(self.sheet)
        assert ProfileTextVersion.objects.filter(
            profile=profile, field="glimpse", text="The lamp went out and I could still see."
        ).exists()

    def test_a_blank_glimpse_writes_no_version(self) -> None:
        response = self.client.post(
            f"{self.base}/staff-magic/", self._payload(glimpse=""), format="json"
        )
        assert response.status_code == 200, response.content[:800]
        assert not ProfileTextVersion.objects.filter(
            profile=self.sheet.true_profile, field="glimpse"
        ).exists()

    def test_options_follow_the_picks_so_far(self) -> None:
        bare = self.client.get(f"{self.base}/staff-magic-options/")
        assert bare.status_code == 200, bare.content[:800]
        assert bare.data["gifts"] == []
        assert bare.data["technique_limit"] == 1
        picked = self.client.get(
            f"{self.base}/staff-magic-options/",
            {"tradition": self.tradition.pk, "gift": self.gift.pk},
        )
        assert [row["id"] for row in picked.data["gifts"]] == [self.gift.pk]
        offered = {row["id"] for row in picked.data["techniques"]}
        assert offered == {self.finished.pk, self.second.pk}
        assert [row["id"] for row in picked.data["resonances"]] == [self.resonance.pk]

    def test_structural_rules_refuse_and_write_nothing(self) -> None:
        refusals = [
            {"techniques": [self.unfinished.pk]},
            {"techniques": [self.stray.pk]},
            {"techniques": [self.finished.pk, self.second.pk]},
            {"techniques": []},
            {"gift": GiftFactory(name="Unoffered Gift").pk},
        ]
        for override in refusals:
            response = self.client.post(
                f"{self.base}/staff-magic/", self._payload(**override), format="json"
            )
            assert response.status_code == 400, (override, response.content[:400])
        assert not CharacterGift.objects.filter(character=self.sheet).exists()
        assert not CharacterTechnique.objects.filter(character=self.sheet).exists()

    def test_a_sheet_without_a_path_is_refused(self) -> None:
        self.path_row.delete()
        response = self.client.post(f"{self.base}/staff-magic/", self._payload(), format="json")
        assert response.status_code == 400
        assert not CharacterGift.objects.filter(character=self.sheet).exists()

    def test_a_sheet_with_a_gift_is_refused(self) -> None:
        self.client.post(f"{self.base}/staff-magic/", self._payload(), format="json")
        again = self.client.post(f"{self.base}/staff-magic/", self._payload(), format="json")
        assert again.status_code == 400
        assert CharacterGift.objects.filter(character=self.sheet).count() == 1

    def test_the_player_cannot_grant_or_list(self) -> None:
        self.client.force_authenticate(user=self.player.account)
        grant = self.client.post(f"{self.base}/staff-magic/", self._payload(), format="json")
        options = self.client.get(f"{self.base}/staff-magic-options/")
        assert grant.status_code in {403, 404}
        assert options.status_code in {403, 404}
        assert not CharacterGift.objects.filter(character=self.sheet).exists()


class GlimpseVersioningTests(TestCase):
    """The Glimpse is prose like the rest: every rewrite keeps the text before it."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(is_staff=True)

    def setUp(self) -> None:
        self.sheet = RosterEntryFactory().character_sheet

    def test_a_rewrite_keeps_the_original(self) -> None:
        aura = CharacterAuraFactory(character=self.sheet, glimpse_story="First light.")
        set_glimpse_prose(aura, "Second light.")
        texts = list(
            ProfileTextVersion.objects.filter(profile=self.sheet.true_profile, field="glimpse")
            .order_by("pk")
            .values_list("text", flat=True)
        )
        assert texts == ["First light.", "Second light."]
        assert CharacterAura.objects.values_list("glimpse_story", flat=True).get(pk=aura.pk) == (
            "Second light."
        )

    def test_staff_edit_patches_the_glimpse(self) -> None:
        CharacterAuraFactory(character=self.sheet, glimpse_story="")
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.patch(
            f"/api/character-sheets/{self.sheet.pk}/staff-edit/",
            {"glimpse": "It was the river."},
            format="json",
        )
        assert response.status_code == 200, response.content[:800]
        assert response.data["staff_edit"]["prose"]["glimpse"] == "It was the river."
        version = ProfileTextVersion.objects.get(
            profile=self.sheet.true_profile, field="glimpse", text="It was the river."
        )
        assert version.edited_by == self.staff

    def test_a_magicless_sheet_refuses_a_glimpse(self) -> None:
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.patch(
            f"/api/character-sheets/{self.sheet.pk}/staff-edit/",
            {"glimpse": "Nothing to hold it."},
            format="json",
        )
        assert response.status_code == 400

    def test_a_staff_edit_and_a_restore_move_the_glimpse_state(self) -> None:
        aura = CharacterAuraFactory(character=self.sheet, glimpse_story="")
        client = APIClient()
        client.force_authenticate(user=self.staff)
        url = f"/api/character-sheets/{self.sheet.pk}"
        client.patch(f"{url}/staff-edit/", {"glimpse": "It was the river."}, format="json")
        assert CharacterAura.objects.values_list("glimpse_state", flat=True).get(pk=aura.pk) == (
            GlimpseState.COMPLETE
        )
        client.patch(f"{url}/staff-edit/", {"glimpse": ""}, format="json")
        assert CharacterAura.objects.values_list("glimpse_state", flat=True).get(pk=aura.pk) == (
            GlimpseState.NOT_STARTED
        )
        first = ProfileTextVersion.objects.get(
            profile=self.sheet.true_profile, field="glimpse", text="It was the river."
        )
        response = client.post(f"{url}/profile-text-versions/{first.pk}/restore/")
        assert response.status_code == 200, response.content[:800]
        assert CharacterAura.objects.values_list("glimpse_story", "glimpse_state").get(
            pk=aura.pk
        ) == ("It was the river.", GlimpseState.COMPLETE)

    def test_restoring_a_glimpse_with_no_aura_is_refused(self) -> None:
        aura = CharacterAuraFactory(character=self.sheet, glimpse_story="Gone now.")
        set_glimpse_prose(aura, "Gone soon.")
        version = ProfileTextVersion.objects.filter(
            profile=self.sheet.true_profile, field="glimpse"
        ).first()
        aura.delete()
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.post(
            f"/api/character-sheets/{self.sheet.pk}/profile-text-versions/{version.pk}/restore/"
        )
        assert response.status_code == 400

    def test_the_aura_admin_versions_a_glimpse_edit(self) -> None:
        aura = CharacterAuraFactory(character=self.sheet, glimpse_story="Before.")
        request = RequestFactory().post("/")
        request.user = self.staff
        # The identity map has already put the new text on the instance by save time.
        aura.glimpse_story = "After."
        form = SimpleNamespace(changed_data=["glimpse_story"], initial={"glimpse_story": "Before."})
        CharacterAuraAdmin(CharacterAura, AdminSite()).save_model(request, aura, form, True)
        texts = list(
            ProfileTextVersion.objects.filter(profile=self.sheet.true_profile, field="glimpse")
            .order_by("pk")
            .values_list("text", flat=True)
        )
        assert texts == ["Before.", "After."]
        assert CharacterAura.objects.values_list("glimpse_state", flat=True).get(pk=aura.pk) == (
            GlimpseState.COMPLETE
        )
