/**
 * AuraSwirl (#5231): a character's aura as one swirling mass of colour, ported from the
 * approved demo. Each colour covers its share of the disc, so the smaller one thins into
 * streaks and wisps as its share falls. A bright mass glows outward; a dark mass keeps a lit
 * rim so it can be seen.
 *
 * The server sends each resonance's colour as `#RRGGBB`. With `secondaryHex` null the mass
 * is one colour and `secondShare` is ignored. It animates while the page is visible, and
 * draws one still frame when the viewer prefers reduced motion.
 */

import { useEffect, useMemo, useRef, type CSSProperties } from 'react';
import { NEUTRAL_HEX, drawMass, hexToOklch, massFrame, type Oklch } from '@/magic/auraSwirl';

/** Pixels per side of the drawing buffer. */
const CANVAS_SIZE = 168;
/** The longest wait between two drawn frames, in milliseconds. */
const FRAME_MS = 33;

export interface AuraSwirlProps {
  primaryHex: string;
  secondaryHex: string | null;
  /** The second colour's share of the mass, 0 to 1. */
  secondShare: number;
  className?: string;
}

const LAYER: CSSProperties = {
  position: 'absolute',
  left: '50%',
  top: '50%',
  transform: 'translate(-50%, -50%)',
  borderRadius: '50%',
};

function parseOrNeutral(hex: string): Oklch {
  try {
    return hexToOklch(hex);
  } catch {
    return hexToOklch(NEUTRAL_HEX);
  }
}

function shareOf(secondary: Oklch | null, secondShare: number): number {
  if (!secondary || !Number.isFinite(secondShare)) return 0;
  return Math.max(0, Math.min(1, secondShare));
}

export function AuraSwirl({ primaryHex, secondaryHex, secondShare, className }: AuraSwirlProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  /** The running clock in seconds; a redraw after a prop change keeps this phase. */
  const clockRef = useRef(0);
  const primary = useMemo(() => parseOrNeutral(primaryHex), [primaryHex]);
  const secondary = useMemo(
    () => (secondaryHex ? parseOrNeutral(secondaryHex) : null),
    [secondaryHex]
  );
  const q = shareOf(secondary, secondShare);
  const frame = useMemo(() => massFrame(primary, secondary, q), [primary, secondary, q]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const still =
      typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (still || typeof requestAnimationFrame !== 'function') {
      drawMass(canvas, primary, secondary, q, 0);
      return undefined;
    }
    let last = 0;
    let handle = 0;
    drawMass(canvas, primary, secondary, q, clockRef.current);
    const tick = (ts: number) => {
      if (ts - last > FRAME_MS && !document.hidden) {
        last = ts;
        clockRef.current = ts / 1000;
        drawMass(canvas, primary, secondary, q, clockRef.current);
      }
      handle = requestAnimationFrame(tick);
    };
    handle = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(handle);
  }, [primary, secondary, q]);

  return (
    <div
      className={className}
      style={{ position: 'relative', width: '100%', aspectRatio: '1 / 1' }}
    >
      <i
        aria-hidden="true"
        data-layer="bloom"
        style={{ ...LAYER, width: '100%', height: '100%', background: frame.bloomBackground }}
      />
      <canvas
        ref={canvasRef}
        width={CANVAS_SIZE}
        height={CANVAS_SIZE}
        aria-hidden="true"
        style={{ ...LAYER, width: '84%', height: '84%' }}
      />
      <i
        aria-hidden="true"
        data-layer="rim"
        style={{
          ...LAYER,
          width: '60%',
          height: '60%',
          border: '2px solid',
          borderColor: frame.rimBorderColor,
          boxShadow: frame.rimBoxShadow,
          opacity: frame.rimOpacity,
        }}
      />
    </div>
  );
}
