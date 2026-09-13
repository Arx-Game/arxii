export interface TierColor {
  bg: string;
  text: string;
  glow: string;
  /** SVG `fill` utility class for the roulette disc's slices. */
  fill: string;
}

// Check outcome faces arrive with `tier_name` equal to the chart outcome
// name ("Critical Failure", "Failure", "Partial Success", "Success",
// "Critical Success"), not the consequence/mission tier names below — so
// each outcome name is keyed here too, reusing the matching color family
// (Critical Failure = Catastrophic, Partial Success = Mixed, Critical
// Success = Spectacular). "Failure" and "Success" are already shared.
export const TIER_COLORS: Record<string, TierColor> = {
  Catastrophic: {
    bg: 'bg-red-900',
    text: 'text-red-100',
    glow: 'shadow-red-500/50',
    fill: 'fill-red-900',
  },
  'Critical Failure': {
    bg: 'bg-red-900',
    text: 'text-red-100',
    glow: 'shadow-red-500/50',
    fill: 'fill-red-900',
  },
  Failure: {
    bg: 'bg-amber-800',
    text: 'text-amber-100',
    glow: 'shadow-amber-500/50',
    fill: 'fill-amber-800',
  },
  Mixed: {
    bg: 'bg-slate-700',
    text: 'text-slate-100',
    glow: 'shadow-slate-400/50',
    fill: 'fill-slate-700',
  },
  'Partial Success': {
    bg: 'bg-slate-700',
    text: 'text-slate-100',
    glow: 'shadow-slate-400/50',
    fill: 'fill-slate-700',
  },
  Success: {
    bg: 'bg-teal-700',
    text: 'text-teal-100',
    glow: 'shadow-teal-500/50',
    fill: 'fill-teal-700',
  },
  Spectacular: {
    bg: 'bg-yellow-600',
    text: 'text-yellow-100',
    glow: 'shadow-yellow-400/50',
    fill: 'fill-yellow-600',
  },
  'Critical Success': {
    bg: 'bg-yellow-600',
    text: 'text-yellow-100',
    glow: 'shadow-yellow-400/50',
    fill: 'fill-yellow-600',
  },
};

export const DEFAULT_TIER_COLOR: TierColor = {
  bg: 'bg-slate-600',
  text: 'text-slate-100',
  glow: 'shadow-slate-400/50',
  fill: 'fill-slate-600',
};

export const ANIMATION_DURATION = {
  TOTAL: 6,
  RESULT_DELAY: 0.5,
};

export const MIN_FULL_ROTATIONS = 4;
