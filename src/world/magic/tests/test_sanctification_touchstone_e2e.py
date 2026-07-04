"""E2E: full Sanctification journey with a touchstone + generic reagents (#707)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase

from actions.definitions.sanctum import SanctumInstallAction
from commands.sanctum import CmdSanctum
from evennia_extensions.factories import CharacterFactory, ObjectDBFactory, RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.items.factories import ItemInstanceFactory
from world.items.models import ItemInstance
from world.locations.constants import HolderType, LocationParentType
from world.locations.factories import LocationOwnershipFactory
from world.magic.factories import CharacterResonanceFactory, ResonanceFactory
from world.magic.models import Ritual, SanctumDetails, SanctumOwnerMode
from world.magic.seeds_checks import ensure_magic_check_content
from world.magic.seeds_sanctum import (
    SANCTIFICATION_PERSONAL_RITUAL_NAME,
    ensure_sanctum_rituals,
)
from world.magic.seeds_touchstone_content import ensure_touchstone_content
from world.room_features.seeds import ensure_sanctum_kind


def _mock_check_success() -> object:
    """Return a fake CheckResult whose outcome tier maps to SUCCESS (success_level=1)."""
    outcome = type("Outcome", (), {"success_level": 1})()
    return type("CheckResult", (), {"outcome": outcome})()


class SanctificationTouchstoneJourneyTests(TestCase):
    """Mirrors test_sanctum_journey_e2e.py's working fixture shape.

    The brief's own test sketch skipped ``ensure_sanctum_kind()`` +
    ``ensure_magic_check_content()`` + the check-roll patch — but
    ``perform_sanctification`` unconditionally rolls the Sanctification
    Ritual's authored check (``perform_ritual_check``) BEFORE creating any
    rows, so those are required for install to succeed at all, independent
    of this task's own touchstone/reagent work.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()

        ensure_sanctum_kind()
        ensure_sanctum_rituals()
        ensure_magic_check_content()

        self._check_patcher = patch("world.checks.services.perform_check")
        mock_check = self._check_patcher.start()
        mock_check.return_value = _mock_check_success()

        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.character.sheet_data = self.sheet
        self.room_profile = RoomProfileFactory()
        self.character.db_location = self.room_profile.objectdb
        self.character.save()
        # Personal Sanctification requires the leader persona to be the room's
        # effective owner (see world.magic.services.sanctum_install
        # ._validate_sanctification_leader) — mirrors
        # test_sanctum_journey_e2e.py's working LocationOwnershipFactory shape
        # (the brief's own sketch used non-existent field names).
        LocationOwnershipFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=self.room_profile,
            holder_type=HolderType.PERSONA,
            holder_persona=self.sheet.primary_persona,
            holder_organization=None,
        )
        self.praedari = ResonanceFactory(name="Praedari")
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.praedari)

        touchstone_template, reagent_templates = ensure_touchstone_content()
        self.ritual = Ritual.objects.get(name=SANCTIFICATION_PERSONAL_RITUAL_NAME)

        self.touchstone = ItemInstanceFactory(
            template=touchstone_template, attuned_to_character_sheet=self.sheet
        )
        self.reagents = [ItemInstanceFactory(template=t) for t in reagent_templates]

    def tearDown(self) -> None:
        self._check_patcher.stop()

    def test_full_journey_consumes_touchstone_and_reagents(self) -> None:
        action = SanctumInstallAction()
        result = action.execute(
            self.character,
            room_profile=self.room_profile,
            resonance=self.praedari,
            owner_mode=SanctumOwnerMode.PERSONAL,
            components_provided=[self.touchstone, *self.reagents],
        )
        assert result.success
        consumed_pks = [self.touchstone.pk, *[r.pk for r in self.reagents]]
        assert not ItemInstance.objects.filter(pk__in=consumed_pks).exists()

    def test_missing_reagents_fails_and_consumes_nothing(self) -> None:
        action = SanctumInstallAction()
        result = action.execute(
            self.character,
            room_profile=self.room_profile,
            resonance=self.praedari,
            owner_mode=SanctumOwnerMode.PERSONAL,
            components_provided=[self.touchstone],
        )
        assert not result.success
        assert ItemInstance.objects.filter(pk=self.touchstone.pk).exists()


def _build_cmd(cmd_cls: type, caller: object, args: str = "") -> object:
    """Instantiate *cmd_cls*, wire *caller*, and prime ``args``/``raw_string``.

    Mirrors the harness pattern in ``test_sanctum_journey_e2e.py``.
    """
    cmd = cmd_cls()
    cmd.caller = caller
    cmd.args = args
    cmd.raw_string = f"{cmd_cls.key} {args}".strip()
    caller.msg = MagicMock()
    return cmd


class SanctumInstallTelnetComponentsE2ETests(TestCase):
    """Step 4a (#707): ``sanctum install`` via the real CmdSanctum command surface.

    Proves the live player-facing telnet path isn't broken by this task's own
    seeded requirements — a player physically carrying the right touchstone +
    reagents (real ObjectDB items in their inventory, not a hand-built
    ``components_provided`` list) can complete ``sanctum install ...`` end to
    end via ``CmdSanctum``, which must gather those carried items itself
    (``CmdSanctum._gather_components``, mirroring
    ``CmdRitual._gather_components``) and forward them as
    ``components_provided`` — the CRITICAL gap the Task 8 reviewer surfaced.
    """

    def setUp(self) -> None:
        from evennia.utils.idmapper.models import flush_cache

        flush_cache()

        ensure_sanctum_kind()
        ensure_sanctum_rituals()
        ensure_magic_check_content()

        self._check_patcher = patch("world.checks.services.perform_check")
        mock_check = self._check_patcher.start()
        mock_check.return_value = _mock_check_success()

        self.character = CharacterFactory()
        self.sheet = CharacterSheetFactory(character=self.character)
        self.character.sheet_data = self.sheet
        self.room_profile = RoomProfileFactory()
        self.character.db_location = self.room_profile.objectdb
        self.character.save()
        LocationOwnershipFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=self.room_profile,
            holder_type=HolderType.PERSONA,
            holder_persona=self.sheet.primary_persona,
            holder_organization=None,
        )
        self.praedari = ResonanceFactory(name="Praedari")
        CharacterResonanceFactory(character_sheet=self.sheet, resonance=self.praedari)

        touchstone_template, reagent_templates = ensure_touchstone_content()

        # Physically carried items: real ObjectDB game objects located inside
        # the caller (self.character.contents), each bound to an ItemInstance
        # via game_object — exactly what CmdSanctum._gather_components walks.
        touchstone_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
        touchstone_obj.location = self.character
        touchstone_obj.save()
        self.touchstone = ItemInstanceFactory(
            template=touchstone_template,
            game_object=touchstone_obj,
            attuned_to_character_sheet=self.sheet,
        )

        self.reagents = []
        for template in reagent_templates:
            reagent_obj = ObjectDBFactory(db_typeclass_path="typeclasses.objects.Object")
            reagent_obj.location = self.character
            reagent_obj.save()
            self.reagents.append(ItemInstanceFactory(template=template, game_object=reagent_obj))

    def tearDown(self) -> None:
        self._check_patcher.stop()

    def test_sanctum_install_consumes_carried_components(self) -> None:
        cmd = _build_cmd(
            CmdSanctum,
            self.character,
            f"install resonance={self.praedari.name} owner=personal",
        )
        cmd.func()

        sanctum = SanctumDetails.objects.filter(founder_character_sheet=self.sheet).first()
        self.assertIsNotNone(
            sanctum, "sanctum install did not create SanctumDetails via the telnet surface"
        )
        consumed_pks = [self.touchstone.pk, *[r.pk for r in self.reagents]]
        self.assertFalse(
            ItemInstance.objects.filter(pk__in=consumed_pks).exists(),
            "carried touchstone/reagents were not consumed by the real CmdSanctum dispatch",
        )

    def test_sanctum_install_fails_without_carried_reagents(self) -> None:
        # Drop the reagents out of the caller's inventory — only the touchstone remains.
        for reagent in self.reagents:
            reagent.game_object.location = None
            reagent.game_object.save()

        cmd = _build_cmd(
            CmdSanctum,
            self.character,
            f"install resonance={self.praedari.name} owner=personal",
        )
        cmd.func()

        self.assertFalse(
            SanctumDetails.objects.filter(founder_character_sheet=self.sheet).exists(),
            "sanctum install should not succeed without the required reagents",
        )
        self.assertTrue(
            ItemInstance.objects.filter(pk=self.touchstone.pk).exists(),
            "touchstone should not be consumed when the ritual overall fails",
        )
