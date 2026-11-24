/**
 * Reaching (#5308): what the "Reaching for" row of a pose holds and what it sends.
 *
 * A pose can say which resonance it reaches for, held or not. An endorsement of the pose then
 * pays that resonance. The row's state is a `ReachDraft`: whether the row is open and which
 * resonance is chosen. The optional field the server takes comes from `reachFields`.
 */

/** The row's switch, and the resonance chosen (null until one is). */
export interface ReachDraft {
  on: boolean;
  resonanceId: number | null;
}

/** The idle row: reaching for nothing. */
export const NO_REACH: ReachDraft = { on: false, resonanceId: null };

/** The field a pose request carries for a reach (none when not reaching). */
export interface ReachFields {
  reach_resonance_id?: number;
}

/** The request fields for the draft: nothing while it is off or no resonance is chosen. */
export function reachFields(draft: ReachDraft): ReachFields {
  if (!draft.on || draft.resonanceId === null) return {};
  return { reach_resonance_id: draft.resonanceId };
}

/** The draft after the writer flips the switch; closing it forgets the choice. */
export function toggleReach(draft: ReachDraft): ReachDraft {
  return draft.on ? NO_REACH : { ...draft, on: true };
}

/** The draft after the writer chooses a resonance (null clears the choice). */
export function chooseReach(draft: ReachDraft, resonanceId: number | null): ReachDraft {
  return { ...draft, resonanceId };
}
