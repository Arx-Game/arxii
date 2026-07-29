"""Sunlight exposure reconciliation: graded severity + tier mapping (#1588, #2846)."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.species.factories import ensure_sunlight_exposure_content
from world.species.services import reconcile_sunlight_exposure
from world.species.sun_constants import BURNING_SEVERITY_THRESHOLD
from world.species.sun_exposure import SunExposure
from world.species.sun_sensitivity import SunSensitivity, sun_severity


def _exposure(base: int = 10, **mitigation: int) -> SunExposure:
    """Build a consistent SunExposure breakdown for mapping tests.

    ``mitigation`` accepts shade / coverage / authored / resonance / magic.
    """
    shade = mitigation.pop("shade", 0)
    coverage = mitigation.pop("coverage", 0)
    authored = mitigation.pop("authored", 0)
    resonance = mitigation.pop("resonance", 0)
    magic = mitigation.pop("magic", 0)
    assert not mitigation, f"unknown mitigation keys: {sorted(mitigation)}"
    residual = max(0, base - shade - coverage - authored - resonance - magic)
    return SunExposure(
        base=base,
        shade=shade,
        coverage=coverage,
        authored_sun=authored,
        resonance_sun=resonance,
        magic=magic,
        residual=residual,
        shade_only_residual=max(0, base - shade),
    )


class SunSeverityTuningInvariantTest(TestCase):
    """The #2846 tuning invariants, locked as named tests over the severity mapping.

    Magnitudes are PLACEHOLDER; these tests pin the *relationships* the design
    promised, so a retune that breaks one fails by name.
    """

    def test_fully_covered_vampire_debuffed_but_undamaged(self):
        """Full non-revealing coverage: bane severity is positive but below Burning."""
        severity = sun_severity(SunSensitivity.BANE, _exposure(coverage=6))
        self.assertGreater(severity, 0)
        self.assertLess(severity, BURNING_SEVERITY_THRESHOLD)

    def test_parasol_plus_shade_zero_vampire_damage_in_public_scene(self):
        """Covered + parasol + shade: still debuffed (severity >= 1), never damaging."""
        severity = sun_severity(SunSensitivity.BANE, _exposure(shade=3, coverage=6, authored=3))
        self.assertGreaterEqual(severity, 1)
        self.assertLess(severity, BURNING_SEVERITY_THRESHOLD)

    def test_vampire_clears_only_when_deeply_shadowed(self):
        """Deep shade clears a vampire entirely; total clothing/magic mitigation never does."""
        cleared = sun_severity(SunSensitivity.BANE, _exposure(shade=8))
        self.assertEqual(cleared, 0)
        clothed_to_zero = sun_severity(
            SunSensitivity.BANE, _exposure(coverage=6, authored=2, magic=2)
        )
        self.assertGreaterEqual(clothed_to_zero, 1)

    def test_skimpy_but_resonance_warded_vampire_shrugs_it_off(self):
        """The sun-flex path (#2377): revealing clothing, big resonance-imbued mitigation.

        Damage fully stopped (severity stays sub-Burning at the bane floor); the
        debuff floor still applies because clothing/magic never clears a bane.
        """
        severity = sun_severity(SunSensitivity.BANE, _exposure(coverage=0, resonance=9))
        self.assertGreaterEqual(severity, 1)
        self.assertLess(severity, BURNING_SEVERITY_THRESHOLD)

    def test_covered_allergy_token_penalty_only(self):
        """A covered dhampir/nox'alfar feels a token penalty at most."""
        severity = sun_severity(SunSensitivity.ALLERGY, _exposure(coverage=6))
        self.assertLessEqual(severity, 1)

    def test_nude_allergy_sunbather_escalates_to_real_peril(self):
        """An unmitigated allergy-tier character reaches a damaging stage."""
        severity = sun_severity(SunSensitivity.ALLERGY, _exposure())
        self.assertGreaterEqual(severity, BURNING_SEVERITY_THRESHOLD)

    def test_night_or_indoors_clears_condition(self):
        """Zero base sun means zero severity for every tier."""
        night = _exposure(base=0)
        self.assertEqual(sun_severity(SunSensitivity.BANE, night), 0)
        self.assertEqual(sun_severity(SunSensitivity.ALLERGY, night), 0)

    def test_none_tier_never_gains_severity(self):
        self.assertEqual(sun_severity(SunSensitivity.NONE, _exposure()), 0)


class ReconcileSunlightExposureTest(TestCase):
    """Unit tests for the reconcile control flow (mapping covered above).

    The full journey (DoT -> peril pipeline) lives in the scenes sunlight E2E.
    """

    @classmethod
    def setUpTestData(cls):
        cls.template = ensure_sunlight_exposure_content()

    def _char(self):
        char = MagicMock()
        char.character_sheet = char.sheet_data
        char.sheet_data.character = char
        return char

    def test_no_sheet_is_noop(self):
        char = MagicMock()
        char.character_sheet = None
        with patch("world.species.services.apply_condition") as ac:
            reconcile_sunlight_exposure(char, room=None)
        ac.assert_not_called()

    def test_none_tier_removes_stale_condition(self):
        """Losing the distinction (or never having one) clears any lingering condition."""
        char = self._char()
        with (
            patch(
                "world.species.sun_sensitivity.sun_sensitivity_for",
                return_value=SunSensitivity.NONE,
            ),
            patch("world.species.services.has_condition", return_value=True),
            patch("world.species.services.remove_condition") as rc,
        ):
            reconcile_sunlight_exposure(char, room=None)
        rc.assert_called_once_with(char, self.template)

    def test_exposed_bane_applies_then_advances_to_computed_severity(self):
        """Fresh exposure: apply at severity 1 (first stage), then advance to target —
        advance re-picks the stage by threshold, keeping stage/severity consistent."""
        char = self._char()
        applied = MagicMock(severity=1)
        with (
            patch(
                "world.species.sun_sensitivity.sun_sensitivity_for",
                return_value=SunSensitivity.BANE,
            ),
            patch(
                "world.species.sun_exposure.felt_sun_exposure",
                return_value=_exposure(),
            ),
            patch(
                "world.species.services._active_sunlight_instance",
                side_effect=[None, applied],
            ),
            patch("world.species.services.apply_condition") as ac,
            patch("world.species.services.advance_condition_severity") as adv,
            patch("world.species.services.ensure_round_for_acute_condition"),
        ):
            reconcile_sunlight_exposure(char, room=MagicMock())
        expected = sun_severity(SunSensitivity.BANE, _exposure())
        ac.assert_called_once_with(char, self.template, severity=1)
        adv.assert_called_once_with(applied, expected - 1)

    def test_severity_delta_advances_existing_instance(self):
        char = self._char()
        instance = MagicMock(severity=2)
        with (
            patch(
                "world.species.sun_sensitivity.sun_sensitivity_for",
                return_value=SunSensitivity.BANE,
            ),
            patch(
                "world.species.sun_exposure.felt_sun_exposure",
                return_value=_exposure(),
            ),
            patch(
                "world.species.services._active_sunlight_instance",
                return_value=instance,
            ),
            patch("world.species.services._sun_escalation_bonus", return_value=0),
            patch("world.species.services.advance_condition_severity") as adv,
            patch("world.species.services.ensure_round_for_acute_condition"),
        ):
            reconcile_sunlight_exposure(char, room=MagicMock())
        expected = sun_severity(SunSensitivity.BANE, _exposure())
        adv.assert_called_once_with(instance, expected - 2)

    def test_severity_delta_decays_existing_instance(self):
        char = self._char()
        instance = MagicMock(severity=9)
        target = sun_severity(SunSensitivity.BANE, _exposure(coverage=6))
        with (
            patch(
                "world.species.sun_sensitivity.sun_sensitivity_for",
                return_value=SunSensitivity.BANE,
            ),
            patch(
                "world.species.sun_exposure.felt_sun_exposure",
                return_value=_exposure(coverage=6),
            ),
            patch(
                "world.species.services._active_sunlight_instance",
                return_value=instance,
            ),
            patch("world.species.services._sun_escalation_bonus", return_value=0),
            patch("world.species.services.decay_condition_severity") as dec,
            patch("world.species.services.ensure_round_for_acute_condition"),
        ):
            reconcile_sunlight_exposure(char, room=MagicMock())
        dec.assert_called_once_with(instance, 9 - target)

    def test_zero_target_removes_active_instance(self):
        char = self._char()
        instance = MagicMock(severity=3)
        with (
            patch(
                "world.species.sun_sensitivity.sun_sensitivity_for",
                return_value=SunSensitivity.BANE,
            ),
            patch(
                "world.species.sun_exposure.felt_sun_exposure",
                return_value=_exposure(base=0),
            ),
            patch(
                "world.species.services._active_sunlight_instance",
                return_value=instance,
            ),
            patch("world.species.services.remove_condition") as rc,
        ):
            reconcile_sunlight_exposure(char, room=MagicMock())
        rc.assert_called_once_with(char, self.template)

    def test_damaging_stage_ensures_danger_round(self):
        char = self._char()
        instance = MagicMock(severity=BURNING_SEVERITY_THRESHOLD)
        with (
            patch(
                "world.species.sun_sensitivity.sun_sensitivity_for",
                return_value=SunSensitivity.ALLERGY,
            ),
            patch(
                "world.species.sun_exposure.felt_sun_exposure",
                return_value=_exposure(),
            ),
            patch(
                "world.species.services._active_sunlight_instance",
                return_value=instance,
            ),
            patch("world.species.services._sun_escalation_bonus", return_value=0),
            patch("world.species.services.advance_condition_severity"),
            patch("world.species.services.decay_condition_severity"),
            patch("world.species.services.ensure_round_for_acute_condition") as er,
        ):
            reconcile_sunlight_exposure(char, room=MagicMock())
        er.assert_called_once_with(char.sheet_data)

    def test_escalation_bonus_folds_into_target(self):
        """Sustained exposure escalates: bonus severity lands in the advance delta."""
        char = self._char()
        instance = MagicMock(severity=5)
        base_target = sun_severity(SunSensitivity.BANE, _exposure())
        with (
            patch(
                "world.species.sun_sensitivity.sun_sensitivity_for",
                return_value=SunSensitivity.BANE,
            ),
            patch(
                "world.species.sun_exposure.felt_sun_exposure",
                return_value=_exposure(),
            ),
            patch(
                "world.species.services._active_sunlight_instance",
                return_value=instance,
            ),
            patch("world.species.services._sun_escalation_bonus", return_value=2),
            patch("world.species.services.advance_condition_severity") as adv,
            patch("world.species.services.ensure_round_for_acute_condition"),
        ):
            reconcile_sunlight_exposure(char, room=MagicMock())
        adv.assert_called_once_with(instance, base_target + 2 - 5)
