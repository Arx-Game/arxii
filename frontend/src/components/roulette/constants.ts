export const TIER_COLORS: Record<string, { bg: string; text: string; glow: string }> = {
  Catastrophic: {
    bg: 'bg-red-900',
    text: 'text-red-100',
    glow: 'shadow-red-500/50',
  },
  Failure: {
    bg: 'bg-amber-800',
    text: 'text-amber-100',
    glow: 'shadow-amber-500/50',
  },
  Mixed: {
    bg: 'bg-slate-700',
    text: 'text-slate-100',
    glow: 'shadow-slate-400/50',
  },
  Success: {
    bg: 'bg-teal-700',
    text: 'text-teal-100',
    glow: 'shadow-teal-500/50',
  },
  Spectacular: {
    bg: 'bg-yellow-600',
    text: 'text-yellow-100',
    glow: 'shadow-yellow-400/50',
  },
};

export const DEFAULT_TIER_COLOR = {
  bg: 'bg-slate-600',
  text: 'text-slate-100',
  glow: 'shadow-slate-400/50',
};

export const ANIMATION_DURATION = {
  SPIN_UP: 0.5,
  FULL_SPEED: 2,
  DECELERATION: 3.5,
  TOTAL: 6,
  RESULT_DELAY: 0.5,
};

export const MIN_FULL_ROTATIONS = 4;
