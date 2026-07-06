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
)
from world.magic.models import SanctumOwnerMode
from world.magic.seeds_checks import ensure_magic_check_content
from world.magic.seeds_sanctum import ensure_sanctification_personal_ritual, ensure_sanctum_rituals
from world.magic.seeds_touchstone_content import ensure_touchstone_content
from world.room_features.seeds import ensure_sanctum_kind
from world.traits.factories import CheckOutcomeFactory


def _mock_check_success() -> object:
    """Return a fake CheckResult wrapping a real SUCCESS-tier CheckOutcome row.

    Mirrors ``test_sanctum_journey_e2e.py``'s helper — the Sanctification ritual
    check is patched to a deterministic SUCCESS so these tests exercise the
    component-validation seam, not the check-roll RNG. Since #1207, the outcome
    must be a real DB row (not a duck-typed stand-in) because
    ``perform_sanctification`` reads ``roll.check_result.outcome.name``.
    """
    outcome = CheckOutcomeFactory(name="InstallComponentsE2E_Success", success_level=1)
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

        # ensure_sanctum_rituals() (above) now attaches the real touchstone-mode
        # + reagent RitualComponentRequirement rows to this ritual (#707) — no
        # manual RitualComponentRequirementFactory call needed here anymore
        # (that was Task 8-era scaffolding for when the ritual had zero rows).
        self.ritual = ensure_sanctification_personal_ritual()

        self.template = ItemTemplateFactory(tied_resonance=self.resonance, resonance_tier=self.tier)
        self.touchstone = ItemInstanceFactory(
            template=self.template, attuned_to_character_sheet=self.sheet
        )
        # Task 9 (#707) attached real reagent requirements to this same ritual via
        # ensure_sanctum_rituals() above — supply matching carried reagents so this
        # test's "install succeeds" path still holds under the now-real requirements.
        _, reagent_templates = ensure_touchstone_content()
        self.reagents = [ItemInstanceFactory(template=t) for t in reagent_templates]

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
            components_provided=[self.touchstone, *self.reagents],
        )
        assert result.success
        consumed_pks = [self.touchstone.pk, *[r.pk for r in self.reagents]]
        assert not ItemInstance.objects.filter(pk__in=consumed_pks).exists()

    def test_perform_sanctification_failure_after_consumption_rolls_back(self) -> None:
        """Regression (final-review Finding 1): a SANCTUM_EXC raised by
        ``perform_sanctification`` AFTER ``resolve_and_consume_ritual_components``
        has already consumed the submitted components must roll back that
        consumption too — not leave the player's touchstone/reagents deleted with
        no Sanctum created.

        Triggers ``SanctificationRoomAlreadyHasFeatureError`` (the easiest
        ``SANCTUM_EXC`` member to force deterministically) by pre-creating a
        ``RoomFeatureInstance`` on the target room before the install attempt --
        components are otherwise fully valid, so consumption itself would
        succeed if not for the wrapping transaction.
        """
        from world.room_features.models import RoomFeatureInstance
        from world.room_features.seeds import ensure_sanctum_kind

        RoomFeatureInstance.objects.create(
            room_profile=self.room_profile, feature_kind=ensure_sanctum_kind(), level=1
        )

        # Capture pks BEFORE execute() — Django's delete collector sets
        # ``.pk = None`` on every instance it collects (even under a bulk
        # queryset .delete()), and since these are idmapper-cached objects,
        # ``self.touchstone``/``self.reagents`` are the SAME Python instances
        # the collector touches. Reading ``.pk`` after execute() would see
        # ``None`` regardless of whether the DB-level delete was rolled back.
        consumed_pks = [self.touchstone.pk, *[r.pk for r in self.reagents]]

        action = SanctumInstallAction()
        result = action.execute(
            self.character,
            room_profile=self.room_profile,
            resonance=self.resonance,
            owner_mode=SanctumOwnerMode.PERSONAL,
            components_provided=[self.touchstone, *self.reagents],
        )
        assert not result.success

        assert ItemInstance.objects.filter(pk__in=consumed_pks).count() == len(consumed_pks)
