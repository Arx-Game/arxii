"""Finalize writes the tie, grants bundled Distinctions, names the asset, seeds the group's
opinion of the new PC (#3660)."""

from django.test import TestCase
from evennia.accounts.models import AccountDB

from world.assets.factories import DistinctionAssetGrantFactory
from world.assets.models import NPCAsset
from world.character_creation.constants import OfferArrival, OfferChapter, QuestionKind
from world.character_creation.factories import (
    DistinctionOfferFactory,
    GroupPromptFactory,
    OriginTemplateFactory,
    OriginTemplateSlotChoiceFactory,
    OriginTemplateSlotFactory,
)
from world.character_creation.models import CharacterOriginSlot
from world.character_creation.services import finalize_character
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.distinctions.factories import DistinctionFactory
from world.distinctions.models import CharacterDistinction
from world.societies.factories import OrganizationFactory
from world.societies.models import OrganizationReputation


class ConnectionFinalizeTest(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="connection_finalize")
        self._setup_finalization_base(
            self, prefix="Connection Finalize", height_min=700, height_max=800
        )

    def test_finalize_writes_tie_grant_asset_and_seed(self) -> None:
        template = OriginTemplateFactory(
            beginning=self.beginnings, allows_name_family=False, allows_no_family=True
        )
        crew = OrganizationFactory(name="the Rouault")
        q1 = GroupPromptFactory(template=template, sort_order=0, name="Family")
        q1.anchor_orgs.add(crew)
        kept = DistinctionFactory(name="Kept Close")
        grant = DistinctionAssetGrantFactory(distinction=kept, asset_display_name="A courier")
        courier = OriginTemplateSlotChoiceFactory(slot=q1, name="Courier", reputation_seed=200)
        DistinctionOfferFactory(
            distinction=kept,
            chapter=OfferChapter.LINEAGE,
            origin_choice=courier,
            arrives_as=OfferArrival.BUNDLED,
        )
        who = OriginTemplateSlotFactory(
            template=template,
            sort_order=1,
            name="Who",
            kind=QuestionKind.PERSON,
            same_anchor_as=q1,
            follow_up_to=q1,
        )
        draft = self._create_base_draft(
            origin_anchors={str(q1.id): crew.id},
            origin_choices={str(q1.id): courier.id},
            origin_figures={str(who.id): "The woman who asked twice"},
        )
        draft.selected_origin_template = template
        draft.save()

        character = finalize_character(draft, add_to_roster=True)
        sheet = character.sheet_data

        rows = {r.slot_id: r for r in CharacterOriginSlot.objects.filter(sheet=sheet)}
        assert rows[q1.id].organization == crew
        assert rows[q1.id].choice == courier
        assert rows[who.id].organization == crew
        assert rows[who.id].figure_name == "The woman who asked twice"

        cd = CharacterDistinction.objects.get(character=sheet, distinction=kept)
        assert cd.source_description == "Courier, the Rouault"

        asset = NPCAsset.objects.get(source_distinction_grant=grant)
        assert asset.asset_persona.name == "The woman who asked twice"

        rep = OrganizationReputation.objects.get(persona=sheet.primary_persona, organization=crew)
        assert rep.value == 200
