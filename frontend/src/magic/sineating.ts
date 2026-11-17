/**
 * Sineating (#5177): what the pose composer's "Sineating" row holds and what it sends.
 *
 * A pose can carry one Sineating: a Sinner's plea to a Sineater who is here, or a Sineater's
 * ritual answering a plea waiting for them. The row's state is a `SineatingDraft`; the three
 * optional fields the pose endpoint takes come from `sineatingFields`.
 */

import type { components } from '@/generated/api';

/** One plea the character can make or answer now, as `GET /api/magic/sineating-options/` lists it. */
export type SineatingOption = components['schemas']['SineatingOption'];
export type SineatingRole = SineatingOption['role'];

/** What the writer has picked: a plea to make or answer, and how many units. */
export interface SineatingDraft {
  option: SineatingOption | null;
  units: number;
}

/** The idle row: nothing picked. */
export const NO_SINEATING: SineatingDraft = { option: null, units: 1 };

/** The fields a pose request carries for a Sineating (none when not Sineating). */
export interface SineatingFields {
  sineating_role?: SineatingRole;
  sineating_partner_id?: number;
  sineating_units?: number;
}

export function isSineating(draft: SineatingDraft): boolean {
  return draft.option !== null;
}

export function sineatingFields(draft: SineatingDraft): SineatingFields {
  if (draft.option === null) return {};
  return {
    sineating_role: draft.option.role,
    sineating_partner_id: draft.option.partner_sheet_id,
    sineating_units: draft.units,
  };
}

/** The same plea as before: the same part, with the same partner. */
export function sameSineatingOption(a: SineatingOption, b: SineatingOption): boolean {
  return a.role === b.role && a.partner_sheet_id === b.partner_sheet_id;
}

/** The option in plain words: who is asked, or whose sins are taken on. */
export function sineatingOptionLabel(option: SineatingOption): string {
  return option.role === 'perform'
    ? `Take on ${option.partner_name}'s sins`
    : `Ask ${option.partner_name} to take on your sins`;
}

/** The draft after the writer picks `option`, or taps it again to clear it. */
export function pickSineating(draft: SineatingDraft, option: SineatingOption): SineatingDraft {
  if (draft.option !== null && sameSineatingOption(draft.option, option)) return NO_SINEATING;
  return { option, units: option.max_units };
}
