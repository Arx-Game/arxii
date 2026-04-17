"""Reactive scars for perception events (Phase 10, Task 40, Tests 19-20).

Tests verify scar-decoration of examined output via the reactive layer.
Both tests are skipped: ExaminedPayload is frozen (immutable), so a scar
cannot mutate the result in-place. Implementing these tests requires either:

  1. Making ExaminedPayload mutable (remove frozen=True), OR
  2. Wiring the EXAMINE_PRE event to a mutable pre-payload, having the scar
     modify a staging dict before ExaminedPayload is constructed, OR
  3. Adding a post-construction decoration hook that the trigger layer can
     call on the result object.

Until one of those design decisions is made, the tests are documented here
so the gap is visible and the intent is preserved.

See flows/events/payloads.py — ExaminedPayload is @dataclass(frozen=True).
"""

from django.test import TestCase

# ---------------------------------------------------------------------------
# Task 40: Examine / perception scars (Tests 19-20)
# ---------------------------------------------------------------------------


class MageSightScarTest(TestCase):
    """Test 19: "Mage Sight" scar appends scar description to at_examined output
    ONLY for targets with abyssal affinity.

    Skipped: ExaminedPayload is @dataclass(frozen=True) in flows/events/payloads.py.
    A reactive scar cannot mutate ExaminedPayload.result in-place. The scar needs
    a mutable payload or a dedicated pre-examine decoration hook to append content.

    Design follow-up: Either unfreeze ExaminedPayload (allowing post-hoc decoration)
    or model Mage Sight as a EXAMINE_PRE handler that annotates the observer's
    perception context before ExaminedPayload is constructed. Until then, the full
    end-to-end test cannot be written.

    Intent:
        observer has Mage Sight scar (trigger on EXAMINED, filter: target has abyssal aura).
        examine(observer, abyssal_target) → result.sections contains scar-appended text.
        examine(observer, non_abyssal_target) → result.sections unchanged.
    """

    def test_mage_sight_appends_to_abyssal_target(self):
        self.skipTest(
            "ExaminedPayload is frozen=True; reactive scars cannot mutate the result. "
            "Design follow-up needed: unfreeze ExaminedPayload or add a EXAMINE_PRE "
            "decoration hook. See flows/events/payloads.py and Task 40 notes."
        )

    def test_near_miss_non_abyssal_target_unchanged(self):
        self.skipTest(
            "ExaminedPayload is frozen=True; reactive scars cannot mutate the result. "
            "Design follow-up needed: unfreeze ExaminedPayload or add a EXAMINE_PRE "
            "decoration hook. See flows/events/payloads.py and Task 40 notes."
        )


class SoulSightScarTest(TestCase):
    """Test 20: "Soul Sight" scar reveals true identity only when target has
    the specific persona-type property.

    Skipped: Same design gap as Test 19. ExaminedPayload is frozen=True, preventing
    scar mutation of the result. Additionally, the persona-type property system
    (linking Properties from world/mechanics to characters) is not yet wired into
    the examine pipeline's payload construction.

    Design follow-up: Two preconditions required before implementing:
      1. ExaminedPayload must be mutable (or a pre-examine hook must exist).
      2. The examine pipeline must include persona/property data in the payload
         so the filter DSL can walk target.persona_type.property.

    Intent:
        observer has Soul Sight scar (trigger on EXAMINED, filter: target has
        "masked-identity" property on their primary persona).
        examine(observer, masked_target) → result contains true identity disclosure.
        examine(observer, unmasked_target) → result unchanged.
    """

    def test_soul_sight_reveals_masked_identity(self):
        self.skipTest(
            "ExaminedPayload is frozen=True; reactive scars cannot mutate the result. "
            "Additionally, persona-type property filtering in the examine payload is "
            "not yet wired. Two design gaps must close before this test can run. "
            "See flows/events/payloads.py and Task 40 notes."
        )

    def test_near_miss_unmasked_target_unchanged(self):
        self.skipTest(
            "ExaminedPayload is frozen=True; reactive scars cannot mutate the result. "
            "Additionally, persona-type property filtering in the examine payload is "
            "not yet wired. Two design gaps must close before this test can run. "
            "See flows/events/payloads.py and Task 40 notes."
        )
