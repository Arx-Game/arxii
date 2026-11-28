/**
 * Reaching and marking (#5308, #5327): what the "Reaching for" row of a pose or a journal entry
 * holds and what it sends.
 *
 * A pose can say which resonance it reaches for, in her aura or not. Alone that is a reach: an
 * endorsement of the pose then pays that resonance. Pointing at one of the writer's recorded
 * acts as well makes it a mark, which pays when it is posted. The row's state is a `ReachDraft`:
 * whether the row is open, which resonance is chosen and which act (null is "Nothing: another
 * player has to endorse it"). The optional fields the server takes come from `reachFields`.
 */

/** The row's switch, the resonance chosen (null until one is) and the act pointed at (or null). */
export interface ReachDraft {
  on: boolean;
  resonanceId: number | null;
  /** The recorded act the writer points at; null when she points at nothing. */
  actId: number | null;
}

/** The idle row: reaching for nothing. */
export const NO_REACH: ReachDraft = { on: false, resonanceId: null, actId: null };

/** The fields a pose or journal request carries for a reach or a mark (none when idle). */
export interface ReachFields {
  reach_resonance_id?: number;
  /** One of the writer's recorded acts; present only for a mark. */
  reach_act_id?: number;
}

/** The request fields for the draft: nothing while it is off or no resonance is chosen. */
export function reachFields(draft: ReachDraft): ReachFields {
  if (!draft.on || draft.resonanceId === null) return {};
  return {
    reach_resonance_id: draft.resonanceId,
    ...(draft.actId !== null ? { reach_act_id: draft.actId } : {}),
  };
}

/** The draft after the writer flips the switch; closing it forgets both choices. */
export function toggleReach(draft: ReachDraft): ReachDraft {
  return draft.on ? NO_REACH : { ...draft, on: true };
}

/** The draft after the writer chooses a resonance (null clears the choice). */
export function chooseReach(draft: ReachDraft, resonanceId: number | null): ReachDraft {
  return { ...draft, resonanceId };
}

/** The draft after the writer points at an act (null points at nothing). */
export function chooseAct(draft: ReachDraft, actId: number | null): ReachDraft {
  return { ...draft, actId };
}

/**
 * A journal entry's row has a resonance chosen but no act (#5327): no one can endorse a journal
 * entry, so it pays only as a mark and the act is required. The pose row never asks for one.
 */
export function isReachActMissing(draft: ReachDraft): boolean {
  return draft.on && draft.resonanceId !== null && draft.actId === null;
}
