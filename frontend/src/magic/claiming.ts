/**
 * Claiming (#5181): what the "Claim" row of a pose or journal entry holds and what it sends.
 *
 * A kindled deed sets some resonance aside. A pose or a journal entry can collect it. The row's
 * state is a `ClaimDraft`: whether the claim is on, and which waiting resonances the writer
 * unticked. Everything waiting starts ticked, so a resonance that begins to wait later is ticked
 * too. The optional fields the server takes come from `claimFields`.
 */

import type { KindledResonance } from '@/magic/types';

/** The claim switch, and the resonances the writer chose to leave for later. */
export interface ClaimDraft {
  on: boolean;
  /** Resonance ids the writer unticked. */
  left: number[];
}

/** The idle row: not claiming. */
export const NO_CLAIM: ClaimDraft = { on: false, left: [] };

/** The fields a pose or journal request carries for a claim (none when not claiming). */
export interface ClaimFields {
  claim?: boolean;
  /** Empty means everything waiting. */
  claim_resonance_ids?: number[];
}

/** The resonances with something waiting. */
export function waitingClaims(rows: readonly KindledResonance[] | undefined): KindledResonance[] {
  return (rows ?? []).filter((row) => row.unclaimed > 0);
}

/** The waiting resonances the writer has ticked. */
export function tickedClaims(
  draft: ClaimDraft,
  waiting: readonly KindledResonance[]
): KindledResonance[] {
  return waiting.filter((row) => !draft.left.includes(row.id));
}

/**
 * The request fields for the draft: nothing while it is off or nothing is ticked, an empty id
 * list when everything waiting is ticked, and the ticked ids otherwise.
 */
export function claimFields(draft: ClaimDraft, waiting: readonly KindledResonance[]): ClaimFields {
  if (!draft.on) return {};
  const ticked = tickedClaims(draft, waiting);
  if (ticked.length === 0) return {};
  if (ticked.length === waiting.length) return { claim: true, claim_resonance_ids: [] };
  return { claim: true, claim_resonance_ids: ticked.map((row) => row.id) };
}

/** The draft after the writer flips the Claim switch. */
export function toggleClaim(draft: ClaimDraft): ClaimDraft {
  return { ...draft, on: !draft.on };
}

/** The draft after the writer ticks or unticks one resonance. */
export function toggleClaimResonance(draft: ClaimDraft, resonanceId: number): ClaimDraft {
  const left = draft.left.includes(resonanceId)
    ? draft.left.filter((id) => id !== resonanceId)
    : [...draft.left, resonanceId];
  return { ...draft, left };
}
