/**
 * Compute the player-facing effective anima cost when a strain commitment is
 * applied on top of a base effective cost.
 *
 * Strain is "extra anima the player commits beyond base cost"; negative strain
 * is meaningless (treated as zero).  The backend enforces the upper bound
 * (anima pool) at resolution time — this helper only handles the display math.
 */
export function computeEffectiveCost(baseEffectiveCost: number, strain: number): number {
  return baseEffectiveCost + Math.max(strain, 0);
}
