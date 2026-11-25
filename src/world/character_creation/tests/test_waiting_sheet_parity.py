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
from world.character_creation.factories import OriginTemplateFactory, enemy_card_entry
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
from world.mechanics.constants import STAT_CATEGORY_NAME
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.societies.factories import OrganizationFactory, VacancyFactory
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
                enemy_card_entry("Parity Grudge"),
            ],
            enemy={
                "kind": "person",
                "organization_id": None,
                "name": "Old Marrin",
                "power_tier": "",
                "degree": "annoyed",
                "why": "I took his seat.",
                "public_line": "Marrin and I do not speak.",
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
        self.assertEqual(len(in_game["distinctions"]), 6)
        self.assertEqual(in_game["identity"]["vacancy"]["name"], "Doorwarden")
        self.assertIsNotNone(in_game["actor_sheet"]["enemy"])
        self.assertIsNotNone(in_game["current_residence"])
        self.assertEqual(len(in_game["skills"]), 1)
        self.assertEqual(len(in_game["goals"]), 1)
        self.assertEqual(len(in_game["actor_sheet"]["introductions"]), 2)
        self.assertEqual(in_game["buffed_stats"], {"charm": 50})
        self.assertEqual(
            [s["label"] for s in in_game["bonuses"][0]["rows"][0]["sources"]],
            ["Parity Alluring on hair", "Parity Alluring on eyes"],
        )
        self.assertIsNotNone(in_game["magic"])
        self.assertTrue(in_game["standing"]["memberships"])
        self.assertTrue(in_game["keyring"])
        self.assertEqual(waiting["purse"], {"balance": 500})
        self.assertEqual(len(waiting["secrets"]), 3)
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
        self.assertEqual([row["name"] for row in waiting["distinctions"]], ["Parity Alluring"])
        self.assertEqual(waiting["stats"], {})
