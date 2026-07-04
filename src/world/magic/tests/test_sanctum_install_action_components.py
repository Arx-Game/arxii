"""E2E: SanctumInstallAction validates/consumes Sanctification's components (#707).

Ritual of Sanctification does NOT dispatch through the generic
``PerformRitualAction`` seam like every other Ritual — it's ``client_hosted=True``
and dispatched via ``SanctumInstallAction`` (``actions/definitions/sanctum.py``),
which calls ``perform_sanctification()`` directly. This test proves
``SanctumInstallAction.execute()`` independently wires in the shared
``resolve_and_consume_ritual_components`` helper (Task 5) so the Sanctification
Ritual's own ``RitualComponentRequirement`` rows are honored even though its
dispatch never touches ``PerformRitualAction``.

Fixture wiring mirrors ``world/magic/tests/test_sanctum_journey_e2e.py``'s
``setUp`` (same install path via a different surface: this test calls
``SanctumInstallAction.execute()`` directly rather than going through
``CmdSanctum``).
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from actions.definitions.sanctum import SanctumInstallAction
from evennia_extensions.factories import CharacterFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory, ItemTemplateFactory
from world.items.models import ItemInstance
from world.locations.constants import HolderType, LocationParentType
from world.locations.factories import LocationOwnershipFactory
from world.magic.factories import (
    CharacterResonanceFactory,
    ResonanceFactory,
    ResonanceTierFactory,
    RitualComponentRequirementFactory,
)
from world.magic.models import SanctumOwnerMode
from world.magic.seeds_checks import ensure_magic_check_content
from world.magic.seeds_sanctum import ensure_sanctification_personal_ritual, ensure_sanctum_rituals
from world.room_features.seeds import ensure_sanctum_kind


def _mock_check_success() -> object:
    """Return a fake CheckResult whose outcome tier maps to SUCCESS (success_level=1).

    Mirrors ``test_sanctum_journey_e2e.py``'s helper — the Sanctification ritual
    check is patched to a deterministic SUCCESS so these tests exercise the
    component-validation seam, not the check-roll RNG.
    """
    outcome = type("Outcome", (), {"success_level": 1})()
    return type("CheckResult", (), {"outcome": outcome})()


class SanctumInstallActionComponentsTests(TestCase):
    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()

        # Seed required content for sanctum rituals and check configs.
        ensure_sanctum_kind()
        ensure_sanctum_rituals()
        ensure_magic_check_content()

        # Patch perform_check for the duration of this test; SUCCESS tier throughout.
        self._check_patcher = patch("world.checks.services.perform_check")
        mock_check = self._check_patcher.start()
        mock_check.return_value = _mock_check_success()

        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.room_profile = RoomProfileFactory()
        self.character.db_location = self.room_profile.objectdb
        self.character.save(update_fields=["db_location"])

        # Room ownership: the founder's PRIMARY persona holds the deed (Personal
        # Sanctification requires direct persona ownership).
        LocationOwnershipFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=self.room_profile,
            holder_type=HolderType.PERSONA,
            holder_persona=self.sheet.primary_persona,
            holder_organization=None,
        )

        self.resonance = ResonanceFactory(name="Praedari")
        self.tier = ResonanceTierFactory(name="Faint", tier_level=1)
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.resonance)

        # Sanctification has zero RitualComponentRequirement rows until Task 9
        # authors them for real — attach a touchstone-mode row here so this test
        # actually exercises the new validation path.
        self.ritual = ensure_sanctification_personal_ritual()
        RitualComponentRequirementFactory(
            ritual=self.ritual, item_template=None, min_touchstone_tier=self.tier
        )

        self.template = ItemTemplateFactory(tied_resonance=self.resonance, resonance_tier=self.tier)
        self.touchstone = ItemInstanceFactory(
            template=self.template, attuned_to_character_sheet=self.sheet
        )

    def tearDown(self) -> None:
        self._check_patcher.stop()

    def test_install_without_required_touchstone_fails(self) -> None:
        action = SanctumInstallAction()
        result = action.execute(
            self.character,
            room_profile=self.room_profile,
            resonance=self.resonance,
            owner_mode=SanctumOwnerMode.PERSONAL,
            components_provided=[],
        )
        assert not result.success

    def test_install_with_touchstone_consumes_it(self) -> None:
        action = SanctumInstallAction()
        result = action.execute(
            self.character,
            room_profile=self.room_profile,
            resonance=self.resonance,
            owner_mode=SanctumOwnerMode.PERSONAL,
            components_provided=[self.touchstone],
        )
        assert result.success
        assert not ItemInstance.objects.filter(pk=self.touchstone.pk).exists()
