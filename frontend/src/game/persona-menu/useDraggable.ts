import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Pointer-drag offset for a floating panel (#4030 Look dialog). Drag starts on the
 * element given `handleProps`; the panel applies `translate(offset)`. No drag library
 * exists in the frontend and one panel does not justify adding one.
 */
export function useDraggable() {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const start = useRef<{ x: number; y: number; ox: number; oy: number } | null>(null);

  const onPointerMove = useCallback((e: PointerEvent) => {
    if (!start.current) return;
    setOffset({
      x: start.current.ox + e.clientX - start.current.x,
      y: start.current.oy + e.clientY - start.current.y,
    });
  }, []);

  const onPointerUp = useCallback(() => {
    start.current = null;
    document.removeEventListener('pointermove', onPointerMove);
    document.removeEventListener('pointerup', onPointerUp);
  }, [onPointerMove]);

  useEffect(() => onPointerUp, [onPointerUp]);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      start.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y };
      document.addEventListener('pointermove', onPointerMove);
      document.addEventListener('pointerup', onPointerUp);
    },
    [offset, onPointerMove, onPointerUp]
  );

  return {
    offset,
    handleProps: { onPointerDown },
    reset: () => setOffset({ x: 0, y: 0 }),
  };
}
