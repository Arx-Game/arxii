"""Phase 4.1 tests: Sanctification + Dissolution + absorb + ritual seeds + CheckType seed."""

from __future__ import annotations

from django.test import TestCase

from world.locations.constants import HolderType, LocationParentType
from world.locations.factories import LocationOwnershipFactory
from world.magic.constants import GainSource, SanctumSlotKind, TargetKind
from world.magic.exceptions import RitualCheckConfigMissing
from world.magic.factories import ResonanceFactory
from world.magic.models import (
    ResonanceGrant,
    SanctumDetails,
    SanctumOwnerMode,
    SanctumPendingPayout,
    Thread,
)
from world.magic.seeds_checks import (
    SANCTUM_DISSOLUTION_CHECK_TYPE_NAME,
    ensure_magic_check_content,
    ensure_magic_check_types,
)
from world.magic.seeds_sanctum import (
    DISSOLUTION_RITUAL_NAME,
    SANCTIFICATION_COVENANT_RITUAL_NAME,
    SANCTIFICATION_PERSONAL_RITUAL_NAME,
    ensure_dissolution_ritual,
    ensure_sanctification_covenant_ritual,
    ensure_sanctification_personal_ritual,
    ensure_sanctum_rituals,
)
from world.magic.services.sanctum_install import (
    DISSOLUTION_RECOVERY_BOTCH,
    DISSOLUTION_RECOVERY_CRIT_SUCCESS,
    DISSOLUTION_RECOVERY_FAILURE,
    DISSOLUTION_RECOVERY_SUCCESS,
    AbsorbNothingPendingError,
    AbsorbNotPhysicallyPresentError,
    SanctificationFounderHasPersonalSanctumError,
    SanctificationLeaderNotOwnerError,
    SanctificationRoomAlreadyHasFeatureError,
    SanctificationRoomNotOwnedError,
    _dissolution_recovery_fraction,
    absorb_sanctum_pool,
    perform_dissolution,
    perform_sanctification,
)
from world.room_features.factories import (
    RoomFeatureInstanceFactory,
    RoomFeatureKindFactory,
)
from world.room_features.models import RoomFeatureInstance


class DissolutionRecoveryMathTests(TestCase):
    """Outcome-tier → recovery-fraction mapping is testable in isolation.

    Canonical tiers (from ritual_checks.outcome_tier): crit ≥2, success ≥1,
    fail >−2, botch ≤−2.
    """

    def test_crit_success_returns_80(self) -> None:
        # Canonical crit threshold is 2 (not the old constant 7).
        self.assertEqual(_dissolution_recovery_fraction(2), DISSOLUTION_RECOVERY_CRIT_SUCCESS)
        self.assertEqual(_dissolution_recovery_fraction(10), DISSOLUTION_RECOVERY_CRIT_SUCCESS)

    def test_success_returns_50(self) -> None:
        # success = ≥1 but <2 on the canonical scale.
        self.assertEqual(_dissolution_recovery_fraction(1), DISSOLUTION_RECOVERY_SUCCESS)

    def test_failure_returns_10(self) -> None:
        # 0 and −1 are FAIL (>−2); −2 is BOTCH (≤−2).
        self.assertEqual(_dissolution_recovery_fraction(0), DISSOLUTION_RECOVERY_FAILURE)
        self.assertEqual(_dissolution_recovery_fraction(-1), DISSOLUTION_RECOVERY_FAILURE)

    def test_botch_returns_0(self) -> None:
        # −2 is the BOTCH boundary (≤−2 → botch).
        self.assertEqual(_dissolution_recovery_fraction(-2), DISSOLUTION_RECOVERY_BOTCH)
        self.assertEqual(_dissolution_recovery_fraction(-3), DISSOLUTION_RECOVERY_BOTCH)
        self.assertEqual(_dissolution_recovery_fraction(-10), DISSOLUTION_RECOVERY_BOTCH)


class RitualSeedTests(TestCase):
    def test_sanctification_personal_idempotent(self) -> None:
        r1 = ensure_sanctification_personal_ritual()
        r2 = ensure_sanctification_personal_ritual()
        self.assertEqual(r1.pk, r2.pk)
        self.assertEqual(r1.name, SANCTIFICATION_PERSONAL_RITUAL_NAME)
        self.assertEqual(r1.execution_kind, "SERVICE")
        self.assertIn("perform_sanctification", r1.service_function_path)
        # PLACEHOLDER convention — prose intentionally tagged for audit
        self.assertIn("PLACEHOLDER", r1.description)
        self.assertIn("PLACEHOLDER", r1.narrative_prose)

    def test_sanctification_covenant_idempotent(self) -> None:
        r1 = ensure_sanctification_covenant_ritual()
        r2 = ensure_sanctification_covenant_ritual()
        self.assertEqual(r1.pk, r2.pk)
        self.assertEqual(r1.name, SANCTIFICATION_COVENANT_RITUAL_NAME)

    def test_dissolution_idempotent(self) -> None:
        r1 = ensure_dissolution_ritual()
        r2 = ensure_dissolution_ritual()
        self.assertEqual(r1.pk, r2.pk)
        self.assertEqual(r1.name, DISSOLUTION_RITUAL_NAME)
        self.assertIn("perform_dissolution", r1.service_function_path)

    def test_dissolution_check_type_idempotent(self) -> None:
        """ensure_magic_check_types() seeds the Sanctum Dissolution CheckType idempotently."""
        run1 = ensure_magic_check_types()
        run2 = ensure_magic_check_types()
        c1 = run1[SANCTUM_DISSOLUTION_CHECK_TYPE_NAME]
        c2 = run2[SANCTUM_DISSOLUTION_CHECK_TYPE_NAME]
        self.assertEqual(c1.pk, c2.pk)
        self.assertEqual(c1.name, SANCTUM_DISSOLUTION_CHECK_TYPE_NAME)

    def test_orchestrator_seeds_everything_and_links(self) -> None:
        from world.room_features.models import RoomFeatureKindInstallRitual
        from world.room_features.seeds import ensure_sanctum_kind

        ensure_sanctum_kind()
        ensure_sanctum_rituals()

        sanctum_kind = ensure_sanctum_kind()
        links = RoomFeatureKindInstallRitual.objects.filter(feature_kind=sanctum_kind)
        labels = set(links.values_list("variant_label", flat=True))
        self.assertEqual(labels, {"Personal", "Covenant"})


# ---------------------------------------------------------------------------
# Sanctification — Personal happy path / negative gates
# ---------------------------------------------------------------------------


def _setup_personal_sanctification_room(*, resonance=None, owner_in_room=True):
    """Build a room owned by a persona; returns (room_profile, owner_persona, resonance).

    By default the owner's character is positioned in the room so the
    physical-presence check passes. Pass ``owner_in_room=False`` to
    exercise the negative path.
    """
    from evennia_extensions.factories import RoomProfileFactory
    from world.room_features.seeds import ensure_sanctum_kind
    from world.scenes.factories import PersonaFactory

    ensure_sanctum_kind()
    resonance = resonance or ResonanceFactory()
    room_profile = RoomProfileFactory()
    owner = PersonaFactory()
    LocationOwnershipFactory(
        parent_type=LocationParentType.ROOM,
        area=None,
        room_profile=room_profile,
        holder_type=HolderType.PERSONA,
        holder_persona=owner,
        holder_organization=None,
    )
    if owner_in_room:
        character = owner.character_sheet.character
        character.db_location = room_profile.objectdb
        character.save(update_fields=["db_location"])
    return room_profile, owner, resonance


class PerformSanctificationTests(TestCase):
    def test_personal_happy_path(self) -> None:
        room_profile, owner, resonance = _setup_personal_sanctification_room()

        result = perform_sanctification(
            room_profile,
            owner,
            resonance,
            owner_mode=SanctumOwnerMode.PERSONAL,
        )

        details = SanctumDetails.objects.get(pk=result.sanctum_id)
        self.assertEqual(details.owner_mode, SanctumOwnerMode.PERSONAL)
        self.assertEqual(details.resonance_type, resonance)
        self.assertEqual(details.founder_character_sheet, owner.character_sheet)
        instance = RoomFeatureInstance.objects.get(room_profile=room_profile)
        self.assertEqual(instance.level, 1)

    def test_unowned_room_rejected(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.scenes.factories import PersonaFactory

        room_profile = RoomProfileFactory()
        leader = PersonaFactory()
        with self.assertRaises(SanctificationRoomNotOwnedError):
            perform_sanctification(
                room_profile, leader, ResonanceFactory(), owner_mode=SanctumOwnerMode.PERSONAL
            )

    def test_non_owner_personal_sanctification_rejected(self) -> None:
        from world.scenes.factories import PersonaFactory

        room_profile, _owner, resonance = _setup_personal_sanctification_room()
        intruder = PersonaFactory()
        with self.assertRaises(SanctificationLeaderNotOwnerError):
            perform_sanctification(
                room_profile, intruder, resonance, owner_mode=SanctumOwnerMode.PERSONAL
            )

    def test_already_has_feature_rejected(self) -> None:
        room_profile, owner, resonance = _setup_personal_sanctification_room()
        RoomFeatureInstanceFactory(
            room_profile=room_profile,
            feature_kind=RoomFeatureKindFactory(),
        )
        with self.assertRaises(SanctificationRoomAlreadyHasFeatureError):
            perform_sanctification(
                room_profile, owner, resonance, owner_mode=SanctumOwnerMode.PERSONAL
            )

    def test_second_personal_rejected_for_same_character(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory

        room1, owner, resonance = _setup_personal_sanctification_room()
        perform_sanctification(room1, owner, resonance, owner_mode=SanctumOwnerMode.PERSONAL)
        # Setup a second room owned by the same persona; move character there too.
        room2 = RoomProfileFactory()
        LocationOwnershipFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=room2,
            holder_type=HolderType.PERSONA,
            holder_persona=owner,
            holder_organization=None,
        )
        character = owner.character_sheet.character
        character.db_location = room2.objectdb
        character.save(update_fields=["db_location"])
        with self.assertRaises(SanctificationFounderHasPersonalSanctumError):
            perform_sanctification(
                room2, owner, ResonanceFactory(), owner_mode=SanctumOwnerMode.PERSONAL
            )


# ---------------------------------------------------------------------------
# Absorb — physical presence + pool draining
# ---------------------------------------------------------------------------


class AbsorbSanctumPoolTests(TestCase):
    def _build_sanctum_with_pool(
        self, *, weaver_in_room: bool, pending_weaving: int = 20, pending_owner_bonus: int = 5
    ):
        """Build a Sanctum + a weaver with the indicated pending pool + location."""
        from evennia_extensions.factories import RoomProfileFactory
        from world.room_features.seeds import ensure_sanctum_kind
        from world.scenes.factories import PersonaFactory

        ensure_sanctum_kind()
        resonance = ResonanceFactory()
        room_profile = RoomProfileFactory()
        owner = PersonaFactory()
        LocationOwnershipFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=room_profile,
            holder_type=HolderType.PERSONA,
            holder_persona=owner,
            holder_organization=None,
        )
        # Place the character in the room first — perform_sanctification's
        # physical-presence check fires before any other validation.
        character = owner.character_sheet.character
        character.db_location = room_profile.objectdb
        character.save(update_fields=["db_location"])
        result = perform_sanctification(
            room_profile, owner, resonance, owner_mode=SanctumOwnerMode.PERSONAL
        )
        sanctum = SanctumDetails.objects.get(pk=result.sanctum_id)
        weaver_persona = owner  # owner is also the weaver
        thread = Thread.objects.create(
            owner=weaver_persona.character_sheet,
            resonance=resonance,
            target_kind=TargetKind.SANCTUM,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
        )
        SanctumPendingPayout.objects.create(
            sanctum=sanctum,
            weaver_character_sheet=weaver_persona.character_sheet,
            pending_weaving=pending_weaving,
            pending_owner_bonus=pending_owner_bonus,
        )
        # Now reposition for the absorb-time check (this is the relevant
        # location for the absorb test).
        character.db_location = room_profile.objectdb if weaver_in_room else None
        character.save(update_fields=["db_location"])
        return sanctum, weaver_persona, thread

    def test_absorb_drains_pool_and_creates_grants(self) -> None:
        sanctum, weaver, _thread = self._build_sanctum_with_pool(
            weaver_in_room=True, pending_weaving=20, pending_owner_bonus=5
        )

        result = absorb_sanctum_pool(sanctum, weaver)

        self.assertEqual(result.weaving_drained, 20)
        self.assertEqual(result.owner_bonus_drained, 5)
        self.assertEqual(result.total_drained, 25)
        payout = SanctumPendingPayout.objects.get(
            sanctum=sanctum, weaver_character_sheet=weaver.character_sheet
        )
        self.assertEqual(payout.total_pending(), 0)
        grants = ResonanceGrant.objects.filter(
            character_sheet=weaver.character_sheet,
            source__in=[GainSource.SANCTUM_WEAVING, GainSource.SANCTUM_OWNER_BONUS],
        )
        self.assertEqual(grants.count(), 2)

    def test_absorb_rejected_when_not_in_room(self) -> None:
        sanctum, weaver, _thread = self._build_sanctum_with_pool(weaver_in_room=False)
        with self.assertRaises(AbsorbNotPhysicallyPresentError):
            absorb_sanctum_pool(sanctum, weaver)

    def test_absorb_rejected_when_pool_empty(self) -> None:
        sanctum, weaver, _thread = self._build_sanctum_with_pool(
            weaver_in_room=True, pending_weaving=0, pending_owner_bonus=0
        )
        with self.assertRaises(AbsorbNothingPendingError):
            absorb_sanctum_pool(sanctum, weaver)


# ---------------------------------------------------------------------------
# Dissolution — authored RitualCheckConfig difficulty wiring
# ---------------------------------------------------------------------------


def _build_dissolution_sanctum(*, leader_is_founder: bool = True):
    """Build a Sanctum with seeded rituals + check configs; place the leader.

    Returns (sanctum, leader_persona).
    """
    from evennia_extensions.factories import RoomProfileFactory
    from world.room_features.seeds import ensure_sanctum_kind
    from world.scenes.factories import PersonaFactory

    ensure_sanctum_kind()
    ensure_sanctum_rituals()
    ensure_magic_check_content()

    resonance = ResonanceFactory()
    room_profile = RoomProfileFactory()
    founder = PersonaFactory()
    LocationOwnershipFactory(
        parent_type=LocationParentType.ROOM,
        area=None,
        room_profile=room_profile,
        holder_type=HolderType.PERSONA,
        holder_persona=founder,
        holder_organization=None,
    )
    character = founder.character_sheet.character
    character.db_location = room_profile.objectdb
    character.save(update_fields=["db_location"])
    result = perform_sanctification(
        room_profile, founder, resonance, owner_mode=SanctumOwnerMode.PERSONAL
    )
    sanctum = SanctumDetails.objects.get(pk=result.sanctum_id)

    if leader_is_founder:
        leader = founder
    else:
        leader = PersonaFactory()
        non_founder_char = leader.character_sheet.character
        non_founder_char.db_location = room_profile.objectdb
        non_founder_char.save(update_fields=["db_location"])

    return sanctum, leader


class PerformDissolutionDifficultyTests(TestCase):
    """Dissolution uses authored RitualCheckConfig difficulty."""

    def _mock_check_result(self, success_level: int = 1):
        """Build a lightweight fake CheckResult for patching."""
        outcome = type("O", (), {"success_level": success_level})()
        return type("CR", (), {"outcome": outcome})()

    def test_founder_rolls_difficulty_20(self) -> None:
        from unittest.mock import patch

        sanctum, leader = _build_dissolution_sanctum(leader_is_founder=True)

        # perform_check is lazily imported inside perform_ritual_check; patch
        # the canonical module path where it lives.
        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = self._mock_check_result(success_level=1)
            perform_dissolution(sanctum, leader)
            _args, kwargs = mock_check.call_args
            self.assertEqual(kwargs["target_difficulty"], 20)

    def test_non_founder_rolls_difficulty_40(self) -> None:
        from unittest.mock import patch

        sanctum, leader = _build_dissolution_sanctum(leader_is_founder=False)

        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = self._mock_check_result(success_level=1)
            perform_dissolution(sanctum, leader)
            _args, kwargs = mock_check.call_args
            self.assertEqual(kwargs["target_difficulty"], 40)

    def test_missing_config_raises_ritual_check_config_missing(self) -> None:
        from world.magic.models import RitualCheckConfig

        sanctum, leader = _build_dissolution_sanctum(leader_is_founder=True)
        RitualCheckConfig.objects.filter(ritual__name=DISSOLUTION_RITUAL_NAME).delete()

        with self.assertRaises(RitualCheckConfigMissing):
            perform_dissolution(sanctum, leader)
