"""Phase 4.1 tests: Sanctification + Dissolution + absorb + ritual seeds + CheckType seed."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase

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
    ThreadLevelUnlock,
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
    DissolutionAlreadyDissolvedError,
    SanctificationFounderHasPersonalSanctumError,
    SanctificationLeaderNotCovenantMemberError,
    SanctificationLeaderNotOwnerError,
    SanctificationLeaderRankNotAuthorizedError,
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

    _dissolution_recovery_fraction now takes OutcomeTier directly.
    """

    def test_crit_success_returns_80(self) -> None:
        from world.magic.services.ritual_checks import OutcomeTier

        self.assertEqual(
            _dissolution_recovery_fraction(OutcomeTier.CRIT), DISSOLUTION_RECOVERY_CRIT_SUCCESS
        )

    def test_success_returns_50(self) -> None:
        from world.magic.services.ritual_checks import OutcomeTier

        self.assertEqual(
            _dissolution_recovery_fraction(OutcomeTier.SUCCESS), DISSOLUTION_RECOVERY_SUCCESS
        )

    def test_failure_returns_10(self) -> None:
        from world.magic.services.ritual_checks import OutcomeTier

        self.assertEqual(
            _dissolution_recovery_fraction(OutcomeTier.FAIL), DISSOLUTION_RECOVERY_FAILURE
        )

    def test_botch_returns_0(self) -> None:
        from world.magic.services.ritual_checks import OutcomeTier

        self.assertEqual(
            _dissolution_recovery_fraction(OutcomeTier.BOTCH), DISSOLUTION_RECOVERY_BOTCH
        )


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


def _setup_covenant_sanctification_room(*, leader_rank_can_lead_rituals: bool, resonance=None):
    """Build a room owned by a Covenant's backing Organization; returns
    (room_profile, leader_persona, covenant, resonance).

    The leader's CharacterCovenantRole is active with a rank whose
    can_lead_rituals flag is set per the argument. The leader's character is
    positioned in the room so the physical-presence check (which runs after
    leader validation) doesn't block a happy-path test.
    """
    from evennia_extensions.factories import RoomProfileFactory
    from world.covenants.factories import (
        CharacterCovenantRoleFactory,
        CovenantFactory,
        CovenantRankFactory,
    )
    from world.room_features.seeds import ensure_sanctum_kind
    from world.scenes.factories import PersonaFactory

    ensure_sanctum_kind()
    resonance = resonance or ResonanceFactory()
    covenant = CovenantFactory()
    rank = CovenantRankFactory(covenant=covenant, can_lead_rituals=leader_rank_can_lead_rituals)
    leader = PersonaFactory()
    CharacterCovenantRoleFactory(
        character_sheet=leader.character_sheet,
        covenant=covenant,
        rank=rank,
    )
    room_profile = RoomProfileFactory()
    LocationOwnershipFactory(
        parent_type=LocationParentType.ROOM,
        area=None,
        room_profile=room_profile,
        holder_type=HolderType.ORGANIZATION,
        holder_persona=None,
        holder_organization=covenant.organization,
    )
    character = leader.character_sheet.character
    character.db_location = room_profile.objectdb
    character.save(update_fields=["db_location"])
    return room_profile, leader, covenant, resonance


class PerformSanctificationCovenantLeaderGateTests(TestCase):
    """First-ever coverage of the COVENANT owner_mode leader-authorization path."""

    def setUp(self):
        from unittest.mock import patch

        ensure_sanctum_rituals()
        ensure_magic_check_content()
        self._check_patcher = patch("world.checks.services.perform_check")
        mock_check = self._check_patcher.start()
        mock_check.return_value = _mock_check_result(success_level=1)

    def tearDown(self):
        self._check_patcher.stop()

    def test_member_without_can_lead_rituals_rank_rejected(self) -> None:
        room_profile, leader, _covenant, resonance = _setup_covenant_sanctification_room(
            leader_rank_can_lead_rituals=False
        )
        with self.assertRaises(SanctificationLeaderRankNotAuthorizedError) as ctx:
            perform_sanctification(
                room_profile, leader, resonance, owner_mode=SanctumOwnerMode.COVENANT
            )
        self.assertIn("ritual-leadership authority", ctx.exception.user_message)

    def test_member_with_can_lead_rituals_rank_succeeds(self) -> None:
        room_profile, leader, _covenant, resonance = _setup_covenant_sanctification_room(
            leader_rank_can_lead_rituals=True
        )
        result = perform_sanctification(
            room_profile, leader, resonance, owner_mode=SanctumOwnerMode.COVENANT
        )
        details = SanctumDetails.objects.get(pk=result.sanctum_id)
        self.assertEqual(details.owner_mode, SanctumOwnerMode.COVENANT)

    def test_non_covenant_organization_owned_room_rejected(self) -> None:
        from evennia_extensions.factories import RoomProfileFactory
        from world.room_features.seeds import ensure_sanctum_kind
        from world.scenes.factories import PersonaFactory
        from world.societies.factories import OrganizationFactory

        ensure_sanctum_kind()
        leader = PersonaFactory()
        # OrganizationFactory's org_type defaults to a sequence-named OrganizationType
        # (e.g. "org_type_7"), never "covenant" — see world/societies/factories.py.
        org = OrganizationFactory()
        room_profile = RoomProfileFactory()
        LocationOwnershipFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=room_profile,
            holder_type=HolderType.ORGANIZATION,
            holder_persona=None,
            holder_organization=org,
        )
        with self.assertRaises(SanctificationLeaderNotCovenantMemberError):
            perform_sanctification(
                room_profile, leader, ResonanceFactory(), owner_mode=SanctumOwnerMode.COVENANT
            )

    def test_covenant_ownership_not_allowed_by_catalog_rejected(self) -> None:
        from world.room_features.constants import RoomFeatureOwnerType
        from world.room_features.models import RoomFeatureKind, RoomFeatureKindOwnerType
        from world.room_features.seeds import SANCTUM_KIND_NAME

        room_profile, leader, _covenant, resonance = _setup_covenant_sanctification_room(
            leader_rank_can_lead_rituals=True
        )
        sanctum_kind = RoomFeatureKind.objects.get(name=SANCTUM_KIND_NAME)
        RoomFeatureKindOwnerType.objects.filter(
            feature_kind=sanctum_kind, owner_type=RoomFeatureOwnerType.ORGANIZATION_COVENANT
        ).delete()
        with self.assertRaises(SanctificationLeaderNotCovenantMemberError):
            perform_sanctification(
                room_profile, leader, resonance, owner_mode=SanctumOwnerMode.COVENANT
            )


class PerformSanctificationTests(TestCase):
    """Existing validation-gate tests — patch perform_check to a deterministic SUCCESS."""

    def setUp(self):
        from unittest.mock import patch

        # Seed the sanctum rituals + check configs so the check can run.
        ensure_sanctum_rituals()
        ensure_magic_check_content()
        # Patch perform_check to success (level=1) so validation tests exercise
        # the pre-check gates that fire before the roll.
        self._check_patcher = patch("world.checks.services.perform_check")
        mock_check = self._check_patcher.start()
        mock_check.return_value = _mock_check_result(success_level=1)

    def tearDown(self):
        self._check_patcher.stop()

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
    def setUp(self):
        from unittest.mock import patch

        ensure_sanctum_rituals()
        ensure_magic_check_content()
        self._check_patcher = patch("world.checks.services.perform_check")
        mock_check = self._check_patcher.start()
        mock_check.return_value = _mock_check_result(success_level=1)

    def tearDown(self):
        self._check_patcher.stop()

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
    Patches perform_check to a deterministic SUCCESS while building the Sanctum
    so the Sanctification check doesn't need real trait data.
    """
    from unittest.mock import patch

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
    with patch("world.checks.services.perform_check") as mock_check:
        mock_check.return_value = _mock_check_result(success_level=1)
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


def _mock_check_result(success_level: int = 1):
    """Build a lightweight fake CheckResult for patching perform_check."""
    outcome = type("O", (), {"success_level": success_level})()
    return type("CR", (), {"outcome": outcome})()


class PerformDissolutionDifficultyTests(TestCase):
    """Dissolution uses authored RitualCheckConfig difficulty."""

    def test_founder_rolls_difficulty_20(self) -> None:
        from unittest.mock import patch

        sanctum, leader = _build_dissolution_sanctum(leader_is_founder=True)

        # perform_check is lazily imported inside perform_ritual_check; patch
        # the canonical module path where it lives.
        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = _mock_check_result(success_level=1)
            perform_dissolution(sanctum, leader)
            _args, kwargs = mock_check.call_args
            self.assertEqual(kwargs["target_difficulty"], 20)

    def test_non_founder_rolls_difficulty_40(self) -> None:
        from unittest.mock import patch

        sanctum, leader = _build_dissolution_sanctum(leader_is_founder=False)

        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = _mock_check_result(success_level=1)
            perform_dissolution(sanctum, leader)
            _args, kwargs = mock_check.call_args
            self.assertEqual(kwargs["target_difficulty"], 40)

    def test_missing_config_raises_ritual_check_config_missing(self) -> None:
        from world.magic.models import RitualCheckConfig

        sanctum, leader = _build_dissolution_sanctum(leader_is_founder=True)
        RitualCheckConfig.objects.filter(ritual__name=DISSOLUTION_RITUAL_NAME).delete()

        with self.assertRaises(RitualCheckConfigMissing):
            perform_dissolution(sanctum, leader)


# ---------------------------------------------------------------------------
# Sanctification — graded check tests
# ---------------------------------------------------------------------------


def _build_sanctification_room_with_seeds():
    """Build a sanctifiable room with seeds present; return (room_profile, owner, resonance)."""
    from evennia_extensions.factories import RoomProfileFactory
    from world.room_features.seeds import ensure_sanctum_kind
    from world.scenes.factories import PersonaFactory

    ensure_sanctum_kind()
    ensure_sanctum_rituals()
    ensure_magic_check_content()

    resonance = ResonanceFactory()
    room_profile = RoomProfileFactory()
    owner = PersonaFactory()
    from world.locations.factories import LocationOwnershipFactory

    LocationOwnershipFactory(
        parent_type=LocationParentType.ROOM,
        area=None,
        room_profile=room_profile,
        holder_type=HolderType.PERSONA,
        holder_persona=owner,
        holder_organization=None,
    )
    character = owner.character_sheet.character
    character.db_location = room_profile.objectdb
    character.save(update_fields=["db_location"])
    return room_profile, owner, resonance


class PerformSanctificationGradedCheckTests(TestCase):
    """Sanctification rolls a graded check; fail/botch → fizzled=True, no rows created."""

    def test_fail_returns_fizzled_and_no_sanctum_created(self) -> None:
        from unittest.mock import patch

        room_profile, owner, resonance = _build_sanctification_room_with_seeds()

        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = _mock_check_result(success_level=0)  # FAIL
            result = perform_sanctification(
                room_profile, owner, resonance, owner_mode=SanctumOwnerMode.PERSONAL
            )

        self.assertTrue(result.fizzled)
        self.assertIsNone(result.sanctum_id)
        self.assertEqual(result.success_level, 0)
        self.assertEqual(result.tier, "fail")
        # No SanctumDetails or RoomFeatureInstance should have been created
        self.assertFalse(
            SanctumDetails.objects.filter(founder_character_sheet=owner.character_sheet).exists()
        )
        from world.room_features.models import RoomFeatureInstance

        self.assertFalse(RoomFeatureInstance.objects.filter(room_profile=room_profile).exists())

    def test_botch_returns_fizzled(self) -> None:
        from unittest.mock import patch

        room_profile, owner, resonance = _build_sanctification_room_with_seeds()

        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = _mock_check_result(success_level=-3)  # BOTCH
            result = perform_sanctification(
                room_profile, owner, resonance, owner_mode=SanctumOwnerMode.PERSONAL
            )

        self.assertTrue(result.fizzled)
        self.assertIsNone(result.sanctum_id)
        self.assertEqual(result.tier, "botch")

    def test_success_creates_sanctum_and_fizzled_false(self) -> None:
        from unittest.mock import patch

        room_profile, owner, resonance = _build_sanctification_room_with_seeds()

        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = _mock_check_result(success_level=1)  # SUCCESS
            result = perform_sanctification(
                room_profile, owner, resonance, owner_mode=SanctumOwnerMode.PERSONAL
            )

        self.assertFalse(result.fizzled)
        self.assertIsNotNone(result.sanctum_id)
        self.assertEqual(result.success_level, 1)
        self.assertTrue(SanctumDetails.objects.filter(pk=result.sanctum_id).exists())

    def test_crit_applies_bonus_homecoming_imbue(self) -> None:
        from unittest.mock import patch

        from world.magic.services.sanctum_install import SANCTIFICATION_CRIT_BONUS_IMBUE
        from world.magic.services.sanctum_lvm import (
            compute_homecoming_cap,
            sum_homecoming_value,
        )

        room_profile, owner, resonance = _build_sanctification_room_with_seeds()

        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = _mock_check_result(success_level=5)  # CRIT
            result = perform_sanctification(
                room_profile, owner, resonance, owner_mode=SanctumOwnerMode.PERSONAL
            )

        self.assertFalse(result.fizzled)
        sanctum = SanctumDetails.objects.get(pk=result.sanctum_id)
        cap = compute_homecoming_cap(sanctum)
        expected_imbue = min(SANCTIFICATION_CRIT_BONUS_IMBUE, cap)
        self.assertEqual(sum_homecoming_value(sanctum), expected_imbue)

    def test_missing_config_raises_ritual_check_config_missing(self) -> None:
        from world.magic.models import RitualCheckConfig

        room_profile, owner, resonance = _build_sanctification_room_with_seeds()
        RitualCheckConfig.objects.filter(ritual__name=SANCTIFICATION_PERSONAL_RITUAL_NAME).delete()

        with self.assertRaises(RitualCheckConfigMissing):
            perform_sanctification(
                room_profile, owner, resonance, owner_mode=SanctumOwnerMode.PERSONAL
            )


class SanctificationFizzleDetailTests(SimpleTestCase):
    """The fizzle detail copy differs by outcome tier — a botch reads darker."""

    def test_fail_and_botch_copy_differ(self) -> None:
        from world.magic.services.ritual_checks import OutcomeTier
        from world.magic.services.sanctum_install import sanctification_fizzle_detail

        fail_copy = sanctification_fizzle_detail(OutcomeTier.FAIL.value)
        botch_copy = sanctification_fizzle_detail(OutcomeTier.BOTCH.value)

        self.assertNotEqual(fail_copy, botch_copy)
        # The ordinary failure keeps the gentle "take hold" framing.
        self.assertIn("take hold", fail_copy)
        # The botch is the darker branch — the rite goes wrong, not merely short.
        self.assertIn("wrong", botch_copy)


# ---------------------------------------------------------------------------
# Dissolution soft-delete invariants
# ---------------------------------------------------------------------------


class PerformDissolutionSoftDeleteTests(TestCase):
    """Dissolution SOFT-deletes the sanctum and SOFT-retires threads.

    Core regression: imbued threads carry PROTECT FKs (ThreadLevelUnlock /
    CombatPullResolvedEffect). The old hard-delete path raised ProtectedError;
    the new path stamps ``dissolved_at`` on the RoomFeatureInstance and
    ``retired_at`` on threads — nothing is deleted.
    """

    def _dissolve_sanctum(self, *, leader_is_founder: bool = True):
        """Build a sanctum + dissolve it; return (sanctum, leader, result)."""
        from unittest.mock import patch

        sanctum, leader = _build_dissolution_sanctum(leader_is_founder=leader_is_founder)
        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = _mock_check_result(success_level=1)
            result = perform_dissolution(sanctum, leader)
        return sanctum, leader, result

    def test_room_feature_instance_still_exists_after_dissolution(self) -> None:
        """RoomFeatureInstance row is preserved (soft-deleted, not hard-deleted)."""
        sanctum, _leader, _result = self._dissolve_sanctum()
        instance = sanctum.feature_instance
        self.assertTrue(
            RoomFeatureInstance.objects.filter(pk=instance.pk).exists(),
            "RoomFeatureInstance was hard-deleted; should be preserved",
        )

    def test_dissolved_at_stamped_on_feature_instance(self) -> None:
        """dissolved_at is set on the RoomFeatureInstance after dissolution."""
        sanctum, _leader, _result = self._dissolve_sanctum()
        instance = RoomFeatureInstance.objects.get(pk=sanctum.feature_instance_id)
        self.assertIsNotNone(
            instance.dissolved_at,
            "RoomFeatureInstance.dissolved_at not set after dissolution",
        )

    def test_sanctum_details_still_exists_after_dissolution(self) -> None:
        """SanctumDetails row is preserved after dissolution."""
        sanctum, _leader, _result = self._dissolve_sanctum()
        self.assertTrue(
            SanctumDetails.objects.filter(pk=sanctum.pk).exists(),
            "SanctumDetails was hard-deleted; should be preserved",
        )

    def test_active_thread_retired_at_stamped_after_dissolution(self) -> None:
        """Active threads targeting the sanctum get retired_at set on dissolution."""
        from unittest.mock import patch

        sanctum, leader = _build_dissolution_sanctum()
        thread = Thread.objects.create(
            owner=leader.character_sheet,
            resonance=sanctum.resonance_type,
            target_kind=TargetKind.SANCTUM,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
        )
        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = _mock_check_result(success_level=1)
            perform_dissolution(sanctum, leader)

        # Use a fresh filter to bypass SharedMemoryModel identity-map cache
        # (queryset .update() does not refresh cached instances).
        self.assertTrue(
            Thread.objects.filter(pk=thread.pk, retired_at__isnull=False).exists(),
            "Thread.retired_at not set after dissolution",
        )
        self.assertTrue(
            Thread.objects.filter(pk=thread.pk).exists(),
            "Thread was hard-deleted; should be preserved",
        )

    def test_imbued_thread_with_level_unlock_no_protected_error(self) -> None:
        """Dissolving a sanctum with an imbued thread (ThreadLevelUnlock) raises no ProtectedError.

        Regression: the old hard-delete path hit ProtectedError via
        ThreadLevelUnlock.thread = on_delete=PROTECT. The soft-retire path leaves
        both the Thread and its ThreadLevelUnlock rows untouched.
        """
        from unittest.mock import patch

        sanctum, leader = _build_dissolution_sanctum()
        thread = Thread.objects.create(
            owner=leader.character_sheet,
            resonance=sanctum.resonance_type,
            target_kind=TargetKind.SANCTUM,
            target_sanctum_details=sanctum,
            slot_kind=SanctumSlotKind.PERSONAL_OWN,
            level=20,
            developed_points=200,
        )
        # Simulate a real imbuing boundary receipt — this is the PROTECT FK that
        # used to crash the hard-delete.
        ThreadLevelUnlock.objects.create(
            thread=thread,
            unlocked_level=20,
            xp_spent=10,
        )

        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = _mock_check_result(success_level=1)
            # This must NOT raise ProtectedError.
            perform_dissolution(sanctum, leader)

        # Thread and its level-unlock survive dissolution.
        # Use fresh filter queries to bypass SharedMemoryModel identity-map cache.
        self.assertTrue(
            Thread.objects.filter(pk=thread.pk, retired_at__isnull=False).exists(),
            "Thread not retired after dissolution",
        )
        self.assertTrue(
            ThreadLevelUnlock.objects.filter(thread=thread).exists(),
            "ThreadLevelUnlock was deleted; should be preserved",
        )
        # Sanctum row still exists, soft-deleted.
        self.assertTrue(
            RoomFeatureInstance.objects.filter(
                pk=sanctum.feature_instance_id, dissolved_at__isnull=False
            ).exists(),
            "RoomFeatureInstance not soft-deleted",
        )

    def test_dissolved_sanctum_excluded_from_sanctum_in_room(self) -> None:
        """sanctum_in_room returns None for a room whose sanctum is dissolved."""
        from actions.definitions.sanctum import sanctum_in_room

        sanctum, _leader, _result = self._dissolve_sanctum()
        room = sanctum.feature_instance.room_profile.objectdb
        self.assertIsNone(
            sanctum_in_room(room),
            "sanctum_in_room returned a dissolved sanctum; should return None",
        )

    def test_idempotency_raises_already_dissolved_error(self) -> None:
        """A second dissolution attempt raises DissolutionAlreadyDissolvedError."""
        from unittest.mock import patch

        sanctum, leader, _result = self._dissolve_sanctum()
        with (
            patch("world.checks.services.perform_check") as mock_check,
            self.assertRaises(DissolutionAlreadyDissolvedError),
        ):
            mock_check.return_value = _mock_check_result(success_level=1)
            perform_dissolution(sanctum, leader)

    def test_founder_can_refound_personal_sanctum_in_different_room(self) -> None:
        """A founder who dissolves their Personal Sanctum can found a new one in a different room.

        Regression: the service pre-check was not excluding dissolved sanctums, so
        re-founding always raised SanctificationFounderHasPersonalSanctumError regardless
        of the room.
        """
        from unittest.mock import patch

        from evennia_extensions.factories import RoomProfileFactory
        from world.room_features.seeds import ensure_sanctum_kind

        # Build + dissolve sanctum in room A (founder is the leader).
        sanctum_a, founder = _build_dissolution_sanctum(leader_is_founder=True)
        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = _mock_check_result(success_level=1)
            perform_dissolution(sanctum_a, founder)

        # Set up room B owned by the same founder.
        ensure_sanctum_kind()
        room_b = RoomProfileFactory()
        LocationOwnershipFactory(
            parent_type=LocationParentType.ROOM,
            area=None,
            room_profile=room_b,
            holder_type=HolderType.PERSONA,
            holder_persona=founder,
            holder_organization=None,
        )
        character = founder.character_sheet.character
        character.db_location = room_b.objectdb
        character.save(update_fields=["db_location"])

        # Re-founding in room B must succeed without SanctificationFounderHasPersonalSanctumError.
        with patch("world.checks.services.perform_check") as mock_check:
            mock_check.return_value = _mock_check_result(success_level=1)
            result = perform_sanctification(
                room_b,
                founder,
                sanctum_a.resonance_type,
                owner_mode=SanctumOwnerMode.PERSONAL,
            )

        self.assertFalse(result.fizzled, "Re-founding after dissolution should succeed")
        self.assertIsNotNone(result.sanctum_id, "New sanctum_id must be set on success")
        new_details = SanctumDetails.objects.get(pk=result.sanctum_id)
        self.assertEqual(new_details.founder_character_sheet, founder.character_sheet)
        self.assertEqual(new_details.owner_mode, SanctumOwnerMode.PERSONAL)
