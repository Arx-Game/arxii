import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { ConsequenceDisplay } from './types';
import {
  TIER_COLORS,
  DEFAULT_TIER_COLOR,
  ANIMATION_DURATION,
  MIN_FULL_ROTATIONS,
} from './constants';

interface RouletteWheelProps {
  consequences: ConsequenceDisplay[];
  onAnimationComplete: () => void;
  skipRequested: boolean;
}

interface Slice {
  consequence: ConsequenceDisplay;
  index: number;
  /** Degrees clockwise from 12 o'clock. */
  startAngle: number;
  sweepAngle: number;
  /** 0-100. */
  percentage: number;
}

// The disc is drawn in its own 260x260 local coordinate space and scaled to
// fit by the enclosing <svg viewBox>, so these are unitless SVG units, not px.
const VIEW_SIZE = 260;
const CENTER = VIEW_SIZE / 2;
const RADIUS = 118;
const HUB_RADIUS = 10;
const LABEL_THRESHOLD_PERCENT = 12;
const LABEL_RADIUS_FACTOR = 0.62;
const LANDING_FRACTION_MIN = 0.2;
const LANDING_FRACTION_MAX = 0.8;
const SPIN_EASE: [number, number, number, number] = [0.12, 0, 0.08, 1];
// A single ink color for every slice label, regardless of theme - the slice
// fills below are fixed saturated colors in both themes, so the label needs
// a fixed light color to read against all of them, not a theme-following one.
const SLICE_LABEL_FILL = 'fill-amber-50';

function getTierFill(tierName: string): string {
  return TIER_COLORS[tierName]?.fill ?? DEFAULT_TIER_COLOR.fill;
}

function getTierSwatch(tierName: string): string {
  return TIER_COLORS[tierName]?.bg ?? DEFAULT_TIER_COLOR.bg;
}

function buildSlices(consequences: ConsequenceDisplay[]): Slice[] {
  const total = consequences.reduce((sum, c) => sum + c.weight, 0);
  let cursor = 0;
  return consequences.map((consequence, index) => {
    const fraction = total > 0 ? consequence.weight / total : 0;
    const sweepAngle = fraction * 360;
    const slice: Slice = {
      consequence,
      index,
      startAngle: cursor,
      sweepAngle,
      percentage: fraction * 100,
    };
    cursor += sweepAngle;
    return slice;
  });
}

function pointOnCircle(angleDeg: number, radius: number): [number, number] {
  // 0 degrees is 12 o'clock; angles increase clockwise.
  const angleRad = ((angleDeg - 90) * Math.PI) / 180;
  return [CENTER + radius * Math.cos(angleRad), CENTER + radius * Math.sin(angleRad)];
}

function buildSlicePath(slice: Slice): string {
  const { startAngle, sweepAngle } = slice;
  // A slice that fills the whole circle has no distinct start/end point on
  // the arc, so it has to be drawn as two half-circle arcs instead of one.
  if (sweepAngle >= 359.99) {
    const [topX, topY] = pointOnCircle(0, RADIUS);
    const [bottomX, bottomY] = pointOnCircle(180, RADIUS);
    return [
      `M ${topX} ${topY}`,
      `A ${RADIUS} ${RADIUS} 0 1 1 ${bottomX} ${bottomY}`,
      `A ${RADIUS} ${RADIUS} 0 1 1 ${topX} ${topY}`,
      'Z',
    ].join(' ');
  }
  const [startX, startY] = pointOnCircle(startAngle, RADIUS);
  const [endX, endY] = pointOnCircle(startAngle + sweepAngle, RADIUS);
  const largeArcFlag = sweepAngle > 180 ? 1 : 0;
  return [
    `M ${CENTER} ${CENTER}`,
    `L ${startX} ${startY}`,
    `A ${RADIUS} ${RADIUS} 0 ${largeArcFlag} 1 ${endX} ${endY}`,
    'Z',
  ].join(' ');
}

function formatPercent(percentage: number): string {
  return `${Math.round(percentage)}%`;
}

export function RouletteWheel({
  consequences,
  onAnimationComplete,
  skipRequested,
}: RouletteWheelProps) {
  const prefersReducedMotion = useReducedMotion();
  const [hasLanded, setHasLanded] = useState(false);
  const hasCompletedRef = useRef(false);

  // Picked once per mount: a random point strictly inside the winning slice,
  // never always its centre.
  const landingFractionRef = useRef<number | null>(null);
  if (landingFractionRef.current === null) {
    landingFractionRef.current =
      LANDING_FRACTION_MIN + Math.random() * (LANDING_FRACTION_MAX - LANDING_FRACTION_MIN);
  }

  const slices = useMemo(() => buildSlices(consequences), [consequences]);

  const selectedSlice = useMemo(
    () => slices.find((slice) => slice.consequence.is_selected) ?? slices[0],
    [slices]
  );

  const landingAngle = useMemo(() => {
    if (!selectedSlice) return 0;
    return (
      selectedSlice.startAngle + selectedSlice.sweepAngle * (landingFractionRef.current ?? 0.5)
    );
  }, [selectedSlice]);

  const targetRotation = useMemo(() => -(MIN_FULL_ROTATIONS * 360 + landingAngle), [landingAngle]);

  const completeOnce = useCallback(() => {
    if (hasCompletedRef.current) return;
    hasCompletedRef.current = true;
    setHasLanded(true);
    onAnimationComplete();
  }, [onAnimationComplete]);

  // Snap straight to the final rotation - never animate - when there is
  // nothing to spin, the user asked to skip, or they prefer reduced motion.
  const snap = slices.length === 0 || skipRequested || Boolean(prefersReducedMotion);

  useEffect(() => {
    if (snap) {
      completeOnce();
    }
  }, [snap, completeOnce]);

  if (slices.length === 0) {
    return null;
  }

  const reversedSlices = [...slices].reverse();

  return (
    <div className="flex w-full flex-col items-center gap-4">
      {/* Fixed pointer */}
      <div
        className="h-0 w-0 border-l-[10px] border-r-[10px] border-t-[14px] border-l-transparent border-r-transparent border-t-primary"
        style={{ marginBottom: '-6px' }}
      />

      <div className="relative w-full max-w-[220px]">
        <motion.div
          key={snap ? 'landed' : 'spinning'}
          initial={{ rotate: snap ? targetRotation : 0 }}
          animate={{ rotate: targetRotation }}
          transition={
            snap ? { duration: 0 } : { duration: ANIMATION_DURATION.TOTAL, ease: SPIN_EASE }
          }
          onAnimationComplete={completeOnce}
          style={{ transformOrigin: '50% 50%' }}
          data-testid="roulette-disc"
          data-landing-angle={landingAngle}
        >
          <svg viewBox={`0 0 ${VIEW_SIZE} ${VIEW_SIZE}`} className="h-auto w-full overflow-visible">
            {slices.map((slice) => (
              <path
                key={`slice-${slice.index}`}
                d={buildSlicePath(slice)}
                className={cn(getTierFill(slice.consequence.tier_name), 'stroke-card')}
                strokeWidth={2}
                data-testid="roulette-slice"
                data-slice-index={slice.index}
                data-slice-label={slice.consequence.label}
                data-slice-start={slice.startAngle}
                data-slice-sweep={slice.sweepAngle}
                data-slice-selected={slice.consequence.is_selected}
              />
            ))}
            {slices
              .filter((slice) => slice.percentage >= LABEL_THRESHOLD_PERCENT)
              .map((slice) => {
                const [labelX, labelY] = pointOnCircle(
                  slice.startAngle + slice.sweepAngle / 2,
                  RADIUS * LABEL_RADIUS_FACTOR
                );
                return (
                  <text
                    key={`label-${slice.index}`}
                    x={labelX}
                    y={labelY}
                    className={cn(SLICE_LABEL_FILL, 'text-[11px] font-semibold')}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    data-testid="wheel-slice-label"
                  >
                    {formatPercent(slice.percentage)}
                  </text>
                );
              })}
            <circle cx={CENTER} cy={CENTER} r={HUB_RADIUS} className="fill-card stroke-border" />
          </svg>
        </motion.div>
      </div>

      <ul className="grid w-full gap-1 text-sm" data-testid="roulette-odds">
        {reversedSlices.map((slice) => {
          const isWinner = hasLanded && slice.consequence.is_selected;
          return (
            <li
              key={`odds-${slice.index}`}
              data-testid="odds-row"
              data-selected={isWinner}
              className={cn(
                'grid grid-cols-[12px_1fr_auto] items-center gap-2 rounded px-1.5 py-0.5',
                isWinner && 'bg-muted font-semibold'
              )}
            >
              <span
                aria-hidden="true"
                className={cn('h-3 w-3 rounded-sm', getTierSwatch(slice.consequence.tier_name))}
              />
              <span className="truncate">{slice.consequence.label}</span>
              <span className="tabular-nums text-muted-foreground" data-testid="odds-percentage">
                {formatPercent(slice.percentage)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
