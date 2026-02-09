import { useEffect, useMemo, useRef, useState } from 'react';
import { motion, useAnimation } from 'framer-motion';
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

function getTierColor(tierName: string) {
  return TIER_COLORS[tierName] ?? DEFAULT_TIER_COLOR;
}

export function RouletteWheel({
  consequences,
  onAnimationComplete,
  skipRequested,
}: RouletteWheelProps) {
  const controls = useAnimation();
  const [hasLanded, setHasLanded] = useState(false);
  const hasStarted = useRef(false);

  const faceCount = consequences.length;

  // Each face occupies (360 / faceCount) degrees
  const degreesPerFace = faceCount > 0 ? 360 / faceCount : 0;

  // Distance from center to face (apothem of the polygon)
  // For a regular polygon with faceCount sides and face width W:
  // apothem = W / (2 * tan(PI / faceCount))
  const faceWidth = 280;
  const apothem = faceCount > 0 ? faceWidth / (2 * Math.tan(Math.PI / faceCount)) : 0;

  // Find which index is selected
  const selectedIndex = useMemo(() => {
    const idx = consequences.findIndex((c) => c.is_selected);
    return idx >= 0 ? idx : 0;
  }, [consequences]);

  // Target rotation: land so the selected face is at front (rotateY = 0 equivalent)
  // The selected face starts at (selectedIndex * degreesPerFace).
  // We need to rotate so it comes to 0 (mod 360), plus extra full rotations.
  const targetRotation = useMemo(() => {
    const faceAngle = selectedIndex * degreesPerFace;
    const fullRotations = MIN_FULL_ROTATIONS * 360;
    // Rotate by full rotations + offset to land on the selected face
    return fullRotations - faceAngle;
  }, [selectedIndex, degreesPerFace]);

  useEffect(() => {
    if (hasStarted.current) return;
    hasStarted.current = true;

    controls
      .start({
        rotateY: targetRotation,
        transition: {
          duration: ANIMATION_DURATION.TOTAL,
          ease: [0.12, 0, 0.08, 1], // slow start, long deceleration tail
        },
      })
      .then(() => {
        setHasLanded(true);
        onAnimationComplete();
      });
  }, [controls, targetRotation, onAnimationComplete]);

  // Skip: snap to final position
  useEffect(() => {
    if (skipRequested && !hasLanded) {
      controls.stop();
      controls.set({ rotateY: targetRotation });
      setHasLanded(true);
      onAnimationComplete();
    }
  }, [skipRequested, hasLanded, controls, targetRotation, onAnimationComplete]);

  // Need at least 3 faces to form a 3D prism
  if (faceCount < 3) {
    return null;
  }

  return (
    <div className="flex flex-col items-center gap-6">
      {/* Pointer indicator */}
      <div className="h-0 w-0 border-l-[10px] border-r-[10px] border-t-[14px] border-l-transparent border-r-transparent border-t-primary" />

      {/* 3D scene container */}
      <div
        className="relative"
        style={{
          width: faceWidth,
          height: 120,
          perspective: 800,
        }}
      >
        <motion.div
          animate={controls}
          style={{
            width: '100%',
            height: '100%',
            position: 'relative',
            transformStyle: 'preserve-3d',
          }}
        >
          {consequences.map((consequence, index) => {
            const color = getTierColor(consequence.tier_name);
            const rotation = index * degreesPerFace;
            const isWinner = index === selectedIndex && hasLanded;

            return (
              <div
                key={`${consequence.label}-${index}`}
                className={cn(
                  'absolute inset-0 flex items-center justify-center rounded-md border border-white/10 px-4',
                  color.bg,
                  color.text,
                  isWinner && `shadow-lg ${color.glow} ring-2 ring-white/60`
                )}
                style={{
                  transform: `rotateY(${rotation}deg) translateZ(${apothem}px)`,
                  backfaceVisibility: 'hidden',
                }}
              >
                <span className="max-w-full truncate text-center text-sm font-medium leading-tight">
                  {consequence.label}
                </span>
              </div>
            );
          })}
        </motion.div>
      </div>
    </div>
  );
}
