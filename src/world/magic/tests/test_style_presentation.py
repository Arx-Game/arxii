"""Tests for STYLE_PRESENTATION gain source and service (Task C1+C2, #1152)."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GainSource
from world.magic.exceptions import EndorsementValidationError
from world.magic.factories import (
    CharacterResonanceFactory,
    MotifFactory,
    MotifResonanceFactory,
    MotifResonanceStyleFactory,
    ResonanceFactory,
    StylePresentationEndorsementFactory,
)
from world.magic.models import ResonanceGrant, StylePresentationEndorsement
from world.magic.services.gain import (
    account_for_sheet,
    create_style_presentation_endorsement,
)
from world.magic.services.resonance import grant_resonance
from world.roster.factories import RosterTenureFactory
from world.scenes.constants import ScenePrivacyMode
from world.scenes.factories import SceneFactory, SceneParticipationFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_worn_style_setup(endorsee_sheet, resonance):
    """Return a Style that is:
    1. Bound to ``resonance`` via the endorsee's MotifResonanceStyle.
    2. Attached to an EquippedItem on the endorsee's character.

    Requires a Character (ObjectDB) on the endorsee_sheet — CharacterSheetFactory
    creates a Character by default, so this should always be satisfied in tests.
    """
    from world.items.constants import BodyRegion, EquipmentLayer
    from world.items.factories import (
        EquippedItemFactory,
        ItemInstanceFactory,
        ItemStyleFactory,
        ItemTemplateFactory,
        QualityTierFactory,
        StyleFactory,
        TemplateSlotFactory,
    )

    style = StyleFactory()
    motif = MotifFactory(character=endorsee_sheet)
    mr = MotifResonanceFactory(motif=motif, resonance=resonance)
    MotifResonanceStyleFactory(motif_resonance=mr, style=style)

    quality = QualityTierFactory(name=f"Worn{style.pk}Common", stat_multiplier="1.00")
    template = ItemTemplateFactory(name=f"WornItem{style.pk}")
    TemplateSlotFactory(
        template=template,
        body_region=BodyRegion.TORSO,
        equipment_layer=EquipmentLayer.BASE,
    )
    item = ItemInstanceFactory(template=template, quality_tier=quality)
    ItemStyleFactory(item_instance=item, style=style, attachment_quality_tier=quality)
    char = endorsee_sheet.character
    EquippedItemFactory(
        character=char,
        item_instance=item,
        body_region=BodyRegion.TORSO,
        equipment_layer=EquipmentLayer.BASE,
    )
    # Invalidate the equipped-items cache so item_styles_for sees the new row.
    char.equipped_items.invalidate()
    return style


# ---------------------------------------------------------------------------
# Model-layer tests: grant_resonance + constraints
# ---------------------------------------------------------------------------


class StylePresentationGrantTest(TestCase):
    """grant_resonance with source=STYLE_PRESENTATION writes balance + ledger row."""

    def test_grant_resonance_raises_balance_and_creates_ledger_row(self):
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        endorsement = StylePresentationEndorsementFactory.create(
            endorsee_sheet=sheet,
            resonance=resonance,
            granted_amount=5,
        )
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=0, lifetime_earned=0
        )

        cr = grant_resonance(
            sheet,
            resonance,
            5,
            source=GainSource.STYLE_PRESENTATION,
            style_presentation_endorsement=endorsement,
        )

        cr.refresh_from_db()
        self.assertEqual(cr.balance, 5)
        self.assertEqual(cr.lifetime_earned, 5)

        grant = ResonanceGrant.objects.get(source=GainSource.STYLE_PRESENTATION)
        self.assertEqual(grant.source_style_presentation_endorsement, endorsement)
        self.assertEqual(grant.amount, 5)
        self.assertEqual(grant.character_sheet, sheet)
        self.assertEqual(grant.resonance, resonance)

    def test_grant_without_endorsement_kwarg_raises_value_error(self):
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=0, lifetime_earned=0
        )

        with self.assertRaises(ValueError):
            grant_resonance(
                sheet,
                resonance,
                5,
                source=GainSource.STYLE_PRESENTATION,
                # no style_presentation_endorsement kwarg → should raise ValueError
            )

    def test_grant_with_wrong_source_kwarg_raises_value_error(self):
        """Passing source=STYLE_PRESENTATION with None endorsement also raises."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        CharacterResonanceFactory(
            character_sheet=sheet, resonance=resonance, balance=0, lifetime_earned=0
        )

        with self.assertRaises(ValueError):
            grant_resonance(
                sheet,
                resonance,
                5,
                source=GainSource.STYLE_PRESENTATION,
                style_presentation_endorsement=None,
            )


class StylePresentationUniqueConstraintTest(TestCase):
    """Duplicate (endorser, endorsee, scene) rows are rejected at the DB level."""

    def test_duplicate_pair_per_scene_raises_integrity_error(self):
        endorser = CharacterSheetFactory()
        endorsee = CharacterSheetFactory()
        scene = SceneFactory()
        resonance = ResonanceFactory()

        StylePresentationEndorsementFactory.create(
            endorser_sheet=endorser,
            endorsee_sheet=endorsee,
            scene=scene,
            resonance=resonance,
        )

        with self.assertRaises(IntegrityError):
            StylePresentationEndorsementFactory.create(
                endorser_sheet=endorser,
                endorsee_sheet=endorsee,
                scene=scene,
                resonance=resonance,
            )


# ---------------------------------------------------------------------------
# Service-layer tests: create_style_presentation_endorsement
# ---------------------------------------------------------------------------


class CreateStylePresentationEndorsementTests(TestCase):
    """Covers all awareness and motif-alignment gates for the service (#1152)."""

    def _build_endorser_with_account(self, *, scene=None, add_participation=True):
        """Return (endorser_sheet, endorser_account). Optionally add participation."""
        tenure = RosterTenureFactory()
        sheet = tenure.roster_entry.character_sheet
        acct = account_for_sheet(sheet)
        if scene is not None and add_participation and acct is not None:
            SceneParticipationFactory(scene=scene, account=acct)
        return sheet, acct

    def _build_full_scenario(
        self,
        *,
        scene_privacy=ScenePrivacyMode.PUBLIC,
        endorser_participates=True,
        same_account=False,
    ):
        """Build a scene + endorser + endorsee with worn style + claimed resonance.

        Returns (endorser_sheet, endorsee_sheet, scene, resonance).
        """
        scene = SceneFactory(privacy_mode=scene_privacy)
        resonance = ResonanceFactory()

        if same_account:
            endorser_tenure = RosterTenureFactory()
            endorser_sheet = endorser_tenure.roster_entry.character_sheet
            endorsee_tenure = RosterTenureFactory(
                player_data=endorser_tenure.player_data,
            )
            endorsee_sheet = endorsee_tenure.roster_entry.character_sheet
        else:
            endorser_tenure = RosterTenureFactory()
            endorser_sheet = endorser_tenure.roster_entry.character_sheet
            endorsee_sheet = CharacterSheetFactory()

        endorser_account = account_for_sheet(endorser_sheet)
        if endorser_participates and endorser_account is not None:
            SceneParticipationFactory(scene=scene, account=endorser_account)

        # Endorsee: claim resonance + wear a bound style.
        CharacterResonanceFactory(character_sheet=endorsee_sheet, resonance=resonance)
        _make_worn_style_setup(endorsee_sheet, resonance)

        return endorser_sheet, endorsee_sheet, scene, resonance

    # ----- happy paths -----------------------------------------

    def test_participant_endorser_fires_grant(self):
        """Present participant → grant fires and balance rises."""
        endorser, endorsee, scene, resonance = self._build_full_scenario(
            scene_privacy=ScenePrivacyMode.PRIVATE,
            endorser_participates=True,
        )
        from world.magic.services.gain import get_resonance_gain_config

        endorsement = create_style_presentation_endorsement(endorser, endorsee, scene, resonance)

        self.assertIsInstance(endorsement, StylePresentationEndorsement)
        cfg = get_resonance_gain_config()
        from world.magic.models import CharacterResonance

        cr = CharacterResonance.objects.get(character_sheet=endorsee, resonance=resonance)
        self.assertEqual(cr.balance, cfg.style_presentation_grant)

    def test_late_joiner_participant_is_eligible(self):
        """Late-joiner (joined after endorsee's entry) is still eligible — no co-presence gate."""
        endorser, endorsee, scene, resonance = self._build_full_scenario(
            scene_privacy=ScenePrivacyMode.PRIVATE,
            endorser_participates=True,
        )
        # Service must not raise even though there is no "entry pose" requirement.
        endorsement = create_style_presentation_endorsement(endorser, endorsee, scene, resonance)
        self.assertIsNotNone(endorsement.pk)

    def test_non_participant_can_endorse_public_scene(self):
        """Non-participant who can VIEW (public scene) → eligible."""
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        resonance = ResonanceFactory()
        # Endorser has no scene participation.
        endorser_tenure = RosterTenureFactory()
        endorser_sheet = endorser_tenure.roster_entry.character_sheet

        endorsee_sheet = CharacterSheetFactory()
        CharacterResonanceFactory(character_sheet=endorsee_sheet, resonance=resonance)
        _make_worn_style_setup(endorsee_sheet, resonance)

        endorsement = create_style_presentation_endorsement(
            endorser_sheet, endorsee_sheet, scene, resonance
        )
        self.assertIsNotNone(endorsement.pk)

    # ----- rejection gates -------------------------------------

    def test_non_viewer_non_participant_rejected(self):
        """Non-viewer, non-participant → EndorsementValidationError."""
        endorser, endorsee, scene, resonance = self._build_full_scenario(
            scene_privacy=ScenePrivacyMode.PRIVATE,
            endorser_participates=False,
        )
        with self.assertRaises(EndorsementValidationError):
            create_style_presentation_endorsement(endorser, endorsee, scene, resonance)

    def test_alt_of_endorsee_rejected(self):
        """Same account → EndorsementValidationError."""
        endorser, endorsee, scene, resonance = self._build_full_scenario(
            same_account=True,
        )
        with self.assertRaises(EndorsementValidationError):
            create_style_presentation_endorsement(endorser, endorsee, scene, resonance)

    def test_resonance_not_bound_to_worn_style_rejected(self):
        """Resonance not bound to any worn style → EndorsementValidationError."""
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        resonance = ResonanceFactory()

        endorser_tenure = RosterTenureFactory()
        endorser_sheet = endorser_tenure.roster_entry.character_sheet
        endorsee_sheet = CharacterSheetFactory()

        CharacterResonanceFactory(character_sheet=endorsee_sheet, resonance=resonance)
        # No MotifResonanceStyle binding → _endorsee_wears_bound_style returns False.

        with self.assertRaises(EndorsementValidationError):
            create_style_presentation_endorsement(endorser_sheet, endorsee_sheet, scene, resonance)

    def test_duplicate_pair_per_scene_rejected(self):
        """Second endorsement on same (endorser, endorsee, scene) → EndorsementValidationError."""
        endorser, endorsee, scene, resonance = self._build_full_scenario()
        create_style_presentation_endorsement(endorser, endorsee, scene, resonance)
        with self.assertRaises(EndorsementValidationError):
            create_style_presentation_endorsement(endorser, endorsee, scene, resonance)

    def test_self_endorsement_rejected(self):
        """endorser == endorsee → EndorsementValidationError."""
        scene = SceneFactory(privacy_mode=ScenePrivacyMode.PUBLIC)
        resonance = ResonanceFactory()
        sheet = CharacterSheetFactory()
        CharacterResonanceFactory(character_sheet=sheet, resonance=resonance)
        _make_worn_style_setup(sheet, resonance)
        with self.assertRaises(EndorsementValidationError):
            create_style_presentation_endorsement(sheet, sheet, scene, resonance)

    def test_writes_ledger_row(self):
        """Successful endorsement creates a ResonanceGrant ledger row."""
        endorser, endorsee, scene, resonance = self._build_full_scenario()
        create_style_presentation_endorsement(endorser, endorsee, scene, resonance)
        self.assertEqual(
            ResonanceGrant.objects.filter(
                source=GainSource.STYLE_PRESENTATION, character_sheet=endorsee
            ).count(),
            1,
        )
