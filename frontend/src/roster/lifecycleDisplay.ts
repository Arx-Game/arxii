/**
 * Shared display rules for `MyRosterEntry.lifecycle_state` (#3412 slice 3).
 *
 * Three surfaces branch on the same lifecycle set — the Hall's
 * `OffscreenActsPlate` (full world-voice refusal prose instead of the act
 * rows), the Hall's `CharactersBand` card meta line, and the app-wide
 * `SelectedCharacterChip` sub-line. They had three copies of the allowed set
 * and two of the short-label map, each carrying a comment saying it "mirrors"
 * another — a mirror that nothing enforced. One definition here removes the
 * drift hazard; the plate keeps its OWN long-form prose, which is a different
 * register and deliberately not shared.
 */

/**
 * The `lifecycle_state` values that still read as "in the story, can still
 * act" — everything else is a degraded state. `COMA` is unwritten anywhere in
 * the codebase (no setter exists, #3412 recon) but is included to mirror the
 * backend gate's own fall-through, not because it's reachable today.
 */
export const ALLOWED_LIFECYCLE_STATES = new Set(['ALIVE', 'COMA']);

/**
 * PLACEHOLDER short state labels for one-line meta text — the condensed form
 * of `OffscreenActsPlate`'s `DEGRADED_STATE_COPY` prose, which does not fit a
 * card meta line or a chip sub-line.
 */
const DEGRADED_STATE_LABELS: Record<string, string> = {
  CAPTURED: 'Held captive',
  DEAD: 'Dead',
  RETIRED: 'Retired',
  UNKNOWN: 'Whereabouts unknown',
};

/** The "Playing: …" fragment for a docked character in a given lifecycle state. */
export function dockedStateLabel(lifecycleState: string): string {
  if (ALLOWED_LIFECYCLE_STATES.has(lifecycleState)) return 'Currently Offscreen';
  return DEGRADED_STATE_LABELS[lifecycleState] ?? 'Currently Offscreen';
}
