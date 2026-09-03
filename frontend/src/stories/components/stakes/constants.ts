/**
 * Shared labels/ladders for the stakes editor (#3561). Duplicated on purpose
 * from `BeatFormDialog.tsx`'s local (unexported) `RISK_LADDER`/`RISK_OPTIONS`
 * - this module needs risk-band comparison for template filtering, which
 * BeatFormDialog's copy doesn't expose.
 */

import type { StakeResolutionColumn, StakeRewardSink, StakeSeverity } from '../../types';

// Mirrors the backend's RenownRisk ladder (`GMLevelCap.risk_index`, #3562).
export const RISK_LADDER = ['none', 'low', 'moderate', 'high', 'extreme'] as const;

export const RISK_LABELS: Record<string, string> = {
  none: 'None',
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  extreme: 'Extreme',
};

export function riskLabel(value: string | null | undefined): string {
  if (!value) return 'None';
  return RISK_LABELS[value] ?? value;
}

/** Index of a risk value on the ladder; unrecognized/blank values sort as 'none'. */
export function riskIndex(value: string | null | undefined): number {
  const i = RISK_LADDER.indexOf((value ?? 'none') as (typeof RISK_LADDER)[number]);
  return i === -1 ? 0 : i;
}

// Mirrors `world.stories.constants.StakeSeverity` label text exactly.
export const SEVERITY_OPTIONS: { value: StakeSeverity; label: string }[] = [
  { value: 1, label: 'Setback' },
  { value: 2, label: 'Costly' },
  { value: 3, label: 'Grave' },
  { value: 4, label: 'Dire' },
  { value: 5, label: 'Removal from play' },
];

export function severityLabel(value: number | null | undefined): string {
  return SEVERITY_OPTIONS.find((o) => o.value === value)?.label ?? String(value ?? '');
}

export const COLUMN_OPTIONS: { value: StakeResolutionColumn; label: string }[] = [
  { value: 'win', label: 'Win' },
  { value: 'loss', label: 'Loss' },
  { value: 'withdrawal', label: 'Withdrawal' },
];

export const COLUMN_LABELS: Record<string, string> = {
  win: 'Win',
  loss: 'Loss',
  withdrawal: 'Withdrawal',
};

// `SetsSubjectLifecycleEnum`/`MachineMatchLifecycleStateEnum` share this ladder.
export const LIFECYCLE_STATE_OPTIONS: { value: string; label: string }[] = [
  { value: 'ALIVE', label: 'Alive' },
  { value: 'CAPTURED', label: 'Captured' },
  { value: 'UNKNOWN', label: 'Whereabouts unknown' },
  { value: 'COMA', label: 'Coma' },
  { value: 'RETIRED', label: 'Retired' },
  { value: 'DEAD', label: 'Dead' },
];

// `AssetTransition` - the three recoverable/terminal AssetStatus values.
export const ASSET_TRANSITION_OPTIONS: { value: string; label: string }[] = [
  { value: 'compromised', label: 'Compromised' },
  { value: 'lost', label: 'Lost' },
  { value: 'dismissed', label: 'Dismissed' },
];

// `StakeRewardLineSinkEnum` (#3566) - a WIN branch's reward-line payout kinds.
export const REWARD_SINK_OPTIONS: { value: StakeRewardSink; label: string }[] = [
  { value: 'money', label: 'Money' },
  { value: 'resonance', label: 'Resonance' },
  { value: 'item', label: 'Item' },
  { value: 'clue', label: 'Clue' },
  { value: 'codex', label: 'Codex entry' },
];
