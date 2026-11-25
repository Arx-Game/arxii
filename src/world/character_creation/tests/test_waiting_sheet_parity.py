"""The waiting sheet reads as the in-game sheet approval makes (#5206).

``build_waiting_sheet`` is built from a submitted draft; the in-game sheet is the character
``approve_application`` makes from the same draft, serialized for its owner. Every key the
in-game payload returns is classified below, so a key added to ``CharacterSheetSerializer``
fails ``test_every_in_game_key_is_classified`` until someone decides what a waiting sheet
shows for it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from django.test import TestCase
from evennia.accounts.models import AccountDB

from evennia_extensions.factories import RoomProfileFactory
from world.buildings.factories import PropertyGrantProfileFactory
from world.buildings.models import Building, BuildingSizeTier
from world.character_creation.constants import (
    BEAT_SECRET_OFFER_IDS,
    TECHNIQUE_PERSONALIZATIONS_KEY,
    OfferChapter,
)
from world.character_creation.factories import (
    DistinctionOfferFactory,
    LifeBeatFactory,
    OriginTemplateFactory,
    enemy_card_entry,
)
from world.character_creation.models import CharacterDraft
from world.character_creation.services import (
    approve_application,
    claim_application,
    submit_draft_for_review,
)
from world.character_creation.sheet_preview import build_waiting_sheet
from world.character_creation.tests.finalization_fixtures import (
    DEFAULT_STATS,
    FinalizationTestMixin,
)
from world.character_sheets.models import Heritage
from world.character_sheets.serializers import (
    CharacterSheetSerializer,
    get_character_sheet_queryset,
)
from world.classes.factories import (
    AspectFactory,
    DistinctionPathAspectGrantFactory,
    PathAspectFactory,
)
from world.currency.models import DistinctionStartingGrant
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.forms.factories import FormTraitFactory, FormTraitOptionFactory
from world.items.constants import GearArchetype
from world.items.factories import ItemTemplateFactory, QualityTierFactory
from world.magic.constants import AFFINITY_CELESTIAL, GiftKind, GlimpseTagAxis
from world.magic.factories import (
    FacetFactory,
    GiftFactory,
    GlimpseTagFactory,
    SignatureMotifBonusFactory,
    TechniqueVariantFactory,
)
from world.magic.models import Affinity
from world.mechanics.constants import STAT_CATEGORY_NAME
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.societies.factories import OrganizationFactory, VacancyFactory
from world.species.factories import SpeciesGiftGrantFactory
from world.traits.models import Trait

#: Built from the draft and compared with the in-game payload after approval.
FILLED_KEYS: tuple[str, ...] = (
    "identity",
    "appearance",
    "stats",
    "buffed_stats",
    "bonuses",
    "skills",
    "path",
    "distinctions",
    "magic",
    "story",
    "goals",
    "beats",
    "standing",
    "actor_sheet",
    "personas",
    "natural_weapons",
    "combat_style",
    "current_residence",
    "domains",
    "keyring",
    # What a new character starts with: its aura's colours, the default plate ink, and the
    # owner's own view of the Gallery.
    "theming",
    "plate_ink",
    "viewer_is_friend",
)
#: Always empty for a new character, and asserted empty after approval.
ALWAYS_EMPTY_KEYS: tuple[str, ...] = (
    "covenants",
    "looks",
    "worn",
    "mentors",
    "ties",
    "ties_ap_this_week",
    "profile_picture",
)
#: Never built by the waiting sheet: staff edit mode's fields, whether the viewer may edit
#: a character that does not exist yet, and its id.
NEVER_BUILT_KEYS: tuple[str, ...] = ("staff_edit", "can_edit", "id")


def _without_ids(value: Any, keys: tuple[str, ...]) -> Any:
    """``value`` with the named keys dropped at every depth.

    A row approval creates has a real id; the waiting sheet numbers it below zero, since
    the row does not exist yet. An Introduction's ``created_at`` is the moment approval
    wrote it. Neither is content the two sheets should agree on, so both are dropped
    before comparing, and only those.
    """
    if isinstance(value, dict):
        return {k: _without_ids(v, keys) for k, v in value.items() if k not in keys}
    if isinstance(value, list):
        return [_without_ids(v, keys) for v in value]
    return value


#: Per key, the fields that name a row approval creates (see ``_without_ids``).
_CREATED_ROW_FIELDS: dict[str, tuple[str, ...]] = {
    "distinctions": ("id",),
    "personas": ("id",),
    "actor_sheet": ("id", "created_at"),
    "keyring": ("id",),
    "magic": ("id",),
    "natural_weapons": ("id",),
    "current_residence": (),
}


def _by_name_then_feature(pair: tuple[str, str]) -> tuple[str, str]:
    """The order a sheet lists held cards in: the card's name, then the feature it is on."""
    name, feature = pair
    return (name.casefold(), feature.casefold())


def waiting_in_pick_order(draft: CharacterDraft) -> list[dict[str, str]]:
    """The draft's cards in the order the player picked them, named as the sheet names them."""
    from world.distinctions.models import Distinction
    from world.forms.models import FormTrait

    cards = Distinction.objects.in_bulk(
        [e["distinction_id"] for e in draft.draft_data["distinctions"]]
    )
    traits = {t.name: t.display_name for t in FormTrait.objects.all()}
    return [
        {
            "name": cards[e["distinction_id"]].name,
            "feature": traits.get(e.get("feature_trait") or "", ""),
        }
        for e in draft.draft_data["distinctions"]
    ]


class WaitingSheetParityTest(FinalizationTestMixin, TestCase):
    """A full draft's waiting sheet equals its owner's in-game sheet after approval."""

    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="waiting_parity")
        self.staff = AccountDB.objects.create(username="waiting_parity_staff", is_staff=True)
        self._setup_finalization_base(self, prefix="Parity", height_min=700, height_max=800)
        # The heritage a Beginnings without one gives, as production holds it.
        Heritage.objects.get_or_create(name="Normal", defaults={"description": "Normal"})
        # A starting area that grants a home in its starting room.
        self.room = RoomProfileFactory()
        self.area.default_starting_room = self.room
        self.area.grants_residence_tenancy = True
        self.area.save()

    def _card(self, name: str, **kwargs: Any):
        return DistinctionFactory(name=name, cost_per_rank=0, **kwargs)

    def _entry(self, card, **extra: Any) -> dict[str, Any]:
        return {
            "distinction_id": card.pk,
            "distinction_name": card.name,
            "rank": 1,
            "cost": 0,
            **extra,
        }

    def _full_draft(self) -> CharacterDraft:
        stat = ModifierCategoryFactory(name=STAT_CATEGORY_NAME)
        charm_target = ModifierTargetFactory(
            name="charm", category=stat, target_trait=Trait.objects.get(name="charm")
        )
        # A card held on two features: two holdings, each adding its effect.
        hair = FormTraitFactory(name="parity_hair", display_name="Hair")
        eyes = FormTraitFactory(name="parity_eyes", display_name="Eyes")
        hair_option = FormTraitOptionFactory(trait=hair, name="red", display_name="Red")
        eyes_option = FormTraitOptionFactory(trait=eyes, name="green", display_name="Green")
        alluring = self._card("Parity Alluring", taken_per_feature=True)
        DistinctionEffectFactory(distinction=alluring, target=charm_target, value_per_rank=10)
        # A card that lands on the Path's stronger Aspect.
        mentor = self._card("Parity Mentor")
        DistinctionPathAspectGrantFactory(distinction=mentor, value=5)
        PathAspectFactory(
            character_path=self.path, aspect=AspectFactory(name="Parity Martial"), weight=2
        )
        # A card that is secret by default, and one that pays a starting purse.
        secret = self._card("Parity Hidden Shame", secret_by_default=True)
        wealthy = self._card("Parity Savings")
        DistinctionStartingGrant.objects.create(distinction=wealthy, coppers=500)
        # A standing vacancy seat on the draft's no-family route.
        org = OrganizationFactory(name="Parity Lodge")
        self.vacancy = VacancyFactory(organization=org, name="Doorwarden", count_remaining=None)
        upbringing = OriginTemplateFactory(
            beginning=self.beginnings, allows_name_family=False, allows_no_family=True
        )
        # A card marked secret on a beat of the life it answers.
        beat = LifeBeatFactory(name="Parity Childhood")
        marked = self._card("Parity Stolen Bread")
        marked_offer = DistinctionOfferFactory(
            distinction=marked, chapter=OfferChapter.BACKGROUNDS, beat=beat
        )
        # A group enemy, whose opinion of the character approval seeds.
        rival = OrganizationFactory(name="Parity Rivals")
        # The species forces a drawback card and gives clawed hands with a facet.
        drawback = self._card("Parity Sun Sickness")
        claws = ItemTemplateFactory(
            name="Parity Claws", gear_archetype=GearArchetype.UNARMED, base_weapon_damage=4
        )
        claws.inherent_facets.add(FacetFactory(name="Parity Keen"))
        QualityTierFactory(name="Parity Common")
        SpeciesGiftGrantFactory(
            species=self.species,
            gift=GiftFactory(
                name="Parity Claw Gift", kind=GiftKind.MINOR, natural_weapon_template=claws
            ),
            drawback_distinction=drawback,
        )
        # The Beginnings grants a property house.
        BuildingSizeTier.objects.get_or_create(tier=1, defaults={"name": "Hut", "space_budget": 50})
        self.beginnings.property_grant_profile = PropertyGrantProfileFactory()
        self.beginnings.save()
        # An early form and a flourish bought in creation, and the flourish after it.
        early = TechniqueVariantFactory(
            parent_technique=self.technique,
            resonance=self.resonance,
            unlock_thread_level=10,
            name_override="Parity Early Flame",
            creation_point_cost=1,
        )
        flourish = SignatureMotifBonusFactory(
            name="Parity Flourish",
            required_resonance=self.resonance,
            min_crossing_level=10,
            creation_point_cost=1,
        )
        SignatureMotifBonusFactory(
            name="Parity Next Flourish", required_resonance=self.resonance, min_crossing_level=30
        )
        # A Glimpse tag that nudges who the character is toward the Celestial.
        tone = GlimpseTagFactory(
            axis=GlimpseTagAxis.TONE,
            name="Parity Radiant",
            affinity=Affinity.objects.get(name=AFFINITY_CELESTIAL),
        )
        draft = self._create_base_draft(
            first_name="Wren",
            # The two holdings of the charm card widen the statistics budget by 20.
            stats={**DEFAULT_STATS, "willpower": 40},
            concept="A doorwarden with a past",
            quote="Mind the step.",
            background="Raised over a tavern.",
            never_do="Betray a guest",
            form_traits={hair.name: hair_option.pk, eyes.name: eyes_option.pk},
            distinctions=[
                self._entry(alluring, feature_trait=hair.name),
                self._entry(alluring, feature_trait=eyes.name),
                self._entry(mentor),
                self._entry(secret),
                self._entry(wealthy),
                self._entry(
                    marked,
                    offer_ids=[marked_offer.pk],
                    arrivals=[marked_offer.arrives_as],
                    sources=[beat.name],
                ),
                enemy_card_entry("Parity Grudge"),
            ],
            beats={str(beat.pk): {BEAT_SECRET_OFFER_IDS: [marked_offer.pk]}},
            enemy={
                "kind": "group",
                "organization_id": rival.pk,
                "name": "",
                "power_tier": "",
                "degree": "annoyed",
                "why": "I took their seat.",
                "public_line": "The Rivals and I do not speak.",
            },
            introductions={
                "application": ["I want to guard doors."],
                "whispers": "Wren once stole a crown.\nWren cannot swim.",
            },
            skills={str(self.skill.pk): 20},
            goals=[
                {
                    "domain_id": ModifierTargetFactory(
                        name="Parity Standing", category=ModifierCategoryFactory(name="goal")
                    ).pk,
                    "points": 5,
                    "notes": "Keep the door.",
                    "horizon": "short_term",
                }
            ],
        )
        draft.selected_origin_template = upbringing
        draft.selected_vacancy = self.vacancy
        draft.draft_data["glimpse_tag_ids"] = [tone.pk]
        draft.draft_data[TECHNIQUE_PERSONALIZATIONS_KEY] = {
            str(self.technique.pk): {
                "early_form_id": early.pk,
                "signature_bonus_id": flourish.pk,
            }
        }
        draft.save()
        return draft

    def _approved_payload(self, draft: CharacterDraft) -> dict[str, Any]:
        errors = {k: v for k, v in draft.get_stage_validation_errors().items() if v}
        self.assertEqual(errors, {})
        application = submit_draft_for_review(draft)
        claim_application(application, reviewer=self.staff)
        approve_application(application, reviewer=self.staff)
        sheet = get_character_sheet_queryset().get(
            roster_entry__tenures__player_data__account=self.account
        )
        request = SimpleNamespace(user=self.account)
        return CharacterSheetSerializer(sheet, context={"request": request}).data

    def test_waiting_sheet_matches_the_approved_sheet(self) -> None:
        draft = self._full_draft()
        waiting = build_waiting_sheet(draft)
        in_game = self._approved_payload(draft)

        for key in FILLED_KEYS:
            fields = _CREATED_ROW_FIELDS.get(key, ())
            with self.subTest(key=key):
                self.assertEqual(
                    _without_ids(waiting[key], fields), _without_ids(in_game[key], fields)
                )
        for key in ALWAYS_EMPTY_KEYS:
            with self.subTest(key=key):
                self.assertFalse(in_game[key])
                self.assertFalse(waiting[key])
        # The cases the fixture is built to cover reached both sheets.
        self.assertEqual(len(in_game["distinctions"]), 8)
        self.assertIn("Parity Sun Sickness", [d["name"] for d in in_game["distinctions"]])
        technique = in_game["magic"]["gifts"][0]["techniques"][0]
        self.assertEqual(
            [form["name"] for form in technique["forms"]],
            [self.technique.name, "Parity Early Flame"],
        )
        self.assertEqual(technique["signature"]["name"], "Parity Flourish")
        self.assertEqual(technique["next_signature"]["name"], "Parity Next Flourish")
        self.assertEqual(
            [share["affinity_name"] for share in in_game["magic"]["aura"]["shares"]],
            ["Primal", "Celestial"],
        )
        (weapon,) = in_game["natural_weapons"]
        self.assertEqual(weapon["facets"], ["Parity Keen"])
        self.assertEqual(
            [row["organization"] for row in in_game["standing"]["reputations"]],
            ["Parity Rivals"],
        )
        self.assertTrue(
            Building.objects.filter(granted_via_profile=self.beginnings.property_grant_profile)
        )
        self.assertEqual(in_game["identity"]["vacancy"]["name"], "Doorwarden")
        self.assertIsNotNone(in_game["actor_sheet"]["enemy"])
        self.assertIsNotNone(in_game["current_residence"])
        self.assertEqual(len(in_game["skills"]), 1)
        self.assertEqual(len(in_game["goals"]), 1)
        self.assertEqual(len(in_game["actor_sheet"]["introductions"]), 2)
        self.assertEqual(in_game["buffed_stats"], {"charm": 50})
        # Both sheets list the cards, and a row's card sources, by name then feature, never
        # in the order the cards were picked or the rows happen to come back from the
        # database (the fixture picks hair before eyes and Mentor before Grudge).
        held = [(row["name"], row["feature"]) for row in in_game["distinctions"]]
        picked = [(row["name"], row["feature"]) for row in waiting_in_pick_order(draft)]
        self.assertNotEqual(picked, sorted(picked, key=_by_name_then_feature))
        self.assertEqual(held, sorted(held, key=_by_name_then_feature))
        self.assertEqual(
            [s["label"] for s in in_game["bonuses"][0]["rows"][0]["sources"]],
            ["Parity Alluring on eyes", "Parity Alluring on hair"],
        )
        self.assertIsNotNone(in_game["magic"])
        self.assertTrue(in_game["standing"]["memberships"])
        self.assertTrue(in_game["keyring"])
        self.assertEqual(waiting["purse"], {"balance": 500})
        # The secret-by-default card, the card marked secret on a beat, two Whispers lines.
        self.assertEqual(len(waiting["secrets"]), 4)
        self.assertIsNone(waiting["staff_edit"])
        self.assertFalse(waiting["can_edit"])

    def test_every_in_game_key_is_classified(self) -> None:
        in_game = self._approved_payload(self._full_draft())
        classified = set(FILLED_KEYS) | set(ALWAYS_EMPTY_KEYS) | set(NEVER_BUILT_KEYS)
        self.assertEqual(classified, set(in_game))

    def test_a_draft_mid_revision_builds_without_error(self) -> None:
        draft = self._full_draft()
        draft.selected_path = None
        draft.draft_data["distinctions"] = [
            *draft.draft_data["distinctions"][:1],
            {"distinction_id": 999_999, "distinction_name": "Removed", "rank": 1, "cost": 0},
        ]
        draft.draft_data.pop("stats", None)
        draft.draft_data.pop("selected_gift_id", None)
        draft.save()

        waiting = build_waiting_sheet(draft)

        self.assertIsNone(waiting["path"])
        self.assertIsNone(waiting["magic"])
        self.assertEqual(
            [row["name"] for row in waiting["distinctions"]],
            ["Parity Alluring", "Parity Sun Sickness"],
        )
        self.assertEqual(waiting["stats"], {})
