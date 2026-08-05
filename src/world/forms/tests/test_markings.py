"""Body markings (#2985): grant seam, coverage visibility, Reveal/Cover, re-conceal hook.

The journey: grant → covered by clothing → hidden from observers (self/staff see
ground truth) → reveal bares it → equipping over it re-conceals → cover tucks it
away by hand. Plus the disguise-overlay leak guard.
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.forms.constants import MarkingKind, MarkingSource
from world.forms.factories import CharacterFormFactory
from world.forms.models import CharacterForm, CharacterFormState, FormMarking, FormType
from world.forms.services.markings import (
    clear_revealed_markings,
    grant_marking,
    visible_markings_for,
)
from world.items.constants import BodyRegion, EquipmentLayer
from world.items.factories import (
    EquippedItemFactory,
    ItemInstanceFactory,
    ItemTemplateFactory,
    TemplateSlotFactory,
)


def _wear(sheet, region, *, revealing=False, layer=EquipmentLayer.BASE):
    """Equip a fresh garment instance at ``region`` and return it."""
    template = ItemTemplateFactory(is_revealing=revealing)
    TemplateSlotFactory(template=template, body_region=region, equipment_layer=layer)
    instance = ItemInstanceFactory(template=template, holder_character_sheet=sheet)
    EquippedItemFactory(
        character=sheet, item_instance=instance, body_region=region, equipment_layer=layer
    )
    sheet.character.equipped_items.invalidate()
    return instance


class GrantMarkingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()

    def test_grant_creates_true_form_and_state_when_absent(self):
        assert not CharacterForm.objects.filter(character=self.sheet).exists()
        marking = grant_marking(
            self.sheet,
            body_region=BodyRegion.TORSO,
            kind=MarkingKind.TATTOO,
            name="a coiled serpent tattoo",
            source=MarkingSource.CHARGEN,
        )
        form = CharacterForm.objects.get(character=self.sheet, form_type=FormType.TRUE)
        assert marking.form_id == form.pk
        state = CharacterFormState.objects.get(character=self.sheet)
        assert state.active_form_id == form.pk

    def test_grant_reuses_existing_true_form(self):
        form = CharacterFormFactory(character=self.sheet, form_type=FormType.TRUE)
        marking = grant_marking(
            self.sheet,
            body_region=BodyRegion.FACE,
            kind=MarkingKind.SCAR,
            name="a duelist's scar",
        )
        assert marking.form_id == form.pk
        assert CharacterForm.objects.filter(character=self.sheet).count() == 1


class MarkingVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.observer = CharacterSheetFactory().character
        cls.marking = grant_marking(
            cls.sheet,
            body_region=BodyRegion.TORSO,
            kind=MarkingKind.TATTOO,
            name="a coiled serpent tattoo",
        )

    def test_bare_skin_shows_marking(self):
        visible = visible_markings_for(self.character, observer=self.observer)
        assert self.marking in visible

    def test_nonrevealing_garment_conceals(self):
        _wear(self.sheet, BodyRegion.TORSO)
        assert visible_markings_for(self.character, observer=self.observer) == []

    def test_self_look_bypasses_concealment(self):
        _wear(self.sheet, BodyRegion.TORSO)
        visible = visible_markings_for(self.character, observer=self.character)
        assert self.marking in visible

    def test_revealing_garment_exposes_marking(self):
        _wear(self.sheet, BodyRegion.TORSO, revealing=True)
        visible = visible_markings_for(self.character, observer=self.observer)
        assert self.marking in visible

    def test_revealing_cut_silhouette_exposes_marking(self):
        """A plunging cut bares the skin even on a non-revealing template (#2985)."""
        from world.items.models import Silhouette, WearFamily

        worn = _wear(self.sheet, BodyRegion.TORSO)
        assert visible_markings_for(self.character, observer=self.observer) == []
        plunging = Silhouette.objects.create(
            name="plunging bodice",
            wear_family=WearFamily.TORSO_GARMENT,
            exposes_skin=True,
        )
        worn.silhouette = plunging
        worn.save(update_fields=["silhouette"])
        visible = visible_markings_for(self.character, observer=self.observer)
        assert self.marking in visible

    def test_garment_elsewhere_does_not_conceal(self):
        _wear(self.sheet, BodyRegion.LEFT_LEG)
        visible = visible_markings_for(self.character, observer=self.observer)
        assert self.marking in visible

    def test_no_form_returns_empty(self):
        stranger = CharacterSheetFactory().character
        assert visible_markings_for(stranger, observer=self.observer) == []

    def test_unpierced_overlay_presents_overlay_markings(self):
        """A disguise never leaks the real form's markings (#2985 leak guard)."""
        disguise = CharacterFormFactory(character=self.sheet, form_type=FormType.DISGUISE)
        # grant_marking already minted the CharacterFormState; the factory's
        # django_get_or_create would silently drop overlay kwargs on the
        # pre-existing row, so set the overlay directly.
        # Mutate through the same accessor the service reads — setUpTestData's
        # per-test deep copies mean a fresh .get() instance and the character's
        # cached form_state are NOT the same object.
        state = self.character.form_state_or_none
        assert state is not None
        state.active_fake_overlay = disguise
        state.save(update_fields=["active_fake_overlay"])
        assert visible_markings_for(self.character, observer=self.observer) == []
        # Ground truth (self) still reads the real form.
        visible = visible_markings_for(self.character, observer=self.character)
        assert self.marking in visible


class RevealCoverMarkingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.observer = CharacterSheetFactory().character
        cls.marking = grant_marking(
            cls.sheet,
            body_region=BodyRegion.TORSO,
            kind=MarkingKind.BRAND,
            name="a crescent brand",
        )
        _wear(cls.sheet, BodyRegion.TORSO)

    def test_reveal_bares_concealed_marking(self):
        from actions.definitions.fashion import RevealAction

        result = RevealAction().run(actor=self.character, marking_id=self.marking.pk)
        assert result.success, result.message
        self.marking.refresh_from_db()
        assert self.marking.revealed_at is not None
        visible = visible_markings_for(self.character, observer=self.observer)
        assert self.marking in visible

    def test_reveal_rejects_uncovered_marking(self):
        from actions.definitions.fashion import RevealAction

        bare = grant_marking(
            self.sheet,
            body_region=BodyRegion.FACE,
            kind=MarkingKind.SCAR,
            name="a duelist's scar",
        )
        result = RevealAction().run(actor=self.character, marking_id=bare.pk)
        assert not result.success

    def test_reveal_rejects_foreign_marking(self):
        from actions.definitions.fashion import RevealAction

        other = grant_marking(
            CharacterSheetFactory(),
            body_region=BodyRegion.TORSO,
            kind=MarkingKind.TATTOO,
            name="someone else's ink",
        )
        result = RevealAction().run(actor=self.character, marking_id=other.pk)
        assert not result.success

    def test_cover_tucks_revealed_marking_away(self):
        from actions.definitions.fashion import CoverUpAction, RevealAction

        RevealAction().run(actor=self.character, marking_id=self.marking.pk)
        result = CoverUpAction().run(actor=self.character, marking_id=self.marking.pk)
        assert result.success, result.message
        self.marking.refresh_from_db()
        assert self.marking.revealed_at is None
        assert visible_markings_for(self.character, observer=self.observer) == []

    def test_cover_rejects_unrevealed_marking(self):
        from actions.definitions.fashion import CoverUpAction

        result = CoverUpAction().run(actor=self.character, marking_id=self.marking.pk)
        assert not result.success

    def test_cover_rejects_when_nothing_conceals(self):
        from actions.definitions.fashion import CoverUpAction

        bare = grant_marking(
            self.sheet,
            body_region=BodyRegion.FACE,
            kind=MarkingKind.RUNE,
            name="a pale rune",
            revealed=True,
        )
        result = CoverUpAction().run(actor=self.character, marking_id=bare.pk)
        assert not result.success

    def test_equipping_over_region_reconceals(self):
        from actions.definitions.fashion import RevealAction
        from world.items.services.equip import equip_item

        RevealAction().run(actor=self.character, marking_id=self.marking.pk)
        template = ItemTemplateFactory()
        TemplateSlotFactory(
            template=template, body_region=BodyRegion.TORSO, equipment_layer=EquipmentLayer.OUTER
        )
        cloak = ItemInstanceFactory(template=template, holder_character_sheet=self.sheet)
        equip_item(
            character_sheet=self.sheet,
            item_instance=cloak,
            body_region=BodyRegion.TORSO,
            equipment_layer=EquipmentLayer.OUTER,
        )
        self.marking.refresh_from_db()
        assert self.marking.revealed_at is None

    def test_clear_revealed_markings_scopes_to_regions(self):
        from world.forms.services.markings import reveal_marking

        reveal_marking(self.marking)
        clear_revealed_markings(self.sheet, {BodyRegion.LEFT_LEG})
        self.marking.refresh_from_db()
        assert self.marking.revealed_at is not None
        clear_revealed_markings(self.sheet, {BodyRegion.TORSO})
        self.marking.refresh_from_db()
        assert self.marking.revealed_at is None


class DraftMarkingMaterializationTests(TestCase):
    def test_finalize_helper_copies_draft_rows(self):
        from world.character_creation.factories import CharacterDraftFactory
        from world.character_creation.models import DraftMarking
        from world.character_creation.services import _materialize_draft_markings

        sheet = CharacterSheetFactory()
        draft = CharacterDraftFactory()
        DraftMarking.objects.create(
            draft=draft,
            body_region=BodyRegion.BACK,
            kind=MarkingKind.TATTOO,
            name="a sprawling back-piece",
            description="PLACEHOLDER ink across both shoulders.",
        )
        _materialize_draft_markings(sheet, draft)
        marking = FormMarking.objects.get(form__character=sheet)
        assert marking.body_region == BodyRegion.BACK
        assert marking.source == MarkingSource.CHARGEN
        assert marking.name == "a sprawling back-piece"
