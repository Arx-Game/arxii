import { useCallback, useEffect, useRef, type PointerEvent, type MouseEvent } from 'react';

/** How long a right-click or a touch is held before it is the menu, not the fold. */
export const HOLD_MS = 350;

export interface LineGestureOptions {
  /** A quick right-click on the text: fold the line, or unfold a folded one. */
  onFold: () => void;
  /** A held press on the text, or a right-click on the avatar: the sorting menu, at the pointer. */
  onMenu: (clientX: number, clientY: number) => void;
  /** False for a view that reads history: no gesture does anything. */
  enabled?: boolean;
  holdMs?: number;
}

export interface LineGestureHandlers {
  onPointerDown: (event: PointerEvent<HTMLElement>) => void;
  onPointerUp: (event: PointerEvent<HTMLElement>) => void;
  onPointerCancel: (event: PointerEvent<HTMLElement>) => void;
  onPointerLeave: (event: PointerEvent<HTMLElement>) => void;
  onContextMenu: (event: MouseEvent<HTMLElement>) => void;
}

interface Press {
  timer: ReturnType<typeof setTimeout>;
  right: boolean;
  opened: boolean;
}

/**
 * The right button and the long-press on a feed line (#4128): the information
 * flow. A quick right-click on the text folds the line (and unfolds a folded
 * one); holding it opens the sorting menu; a right-click on the avatar
 * (`[data-pose-avatar]`) opens the menu at once; a touch held for the same
 * time is the menu too, and a plain tap is nothing, so scrolling on a phone
 * never folds. The browser's own context menu is suppressed on the line.
 *
 * Left-click is play flow and is not read here: the avatar's own menu takes it.
 */
export function useLineGestures({
  onFold,
  onMenu,
  enabled = true,
  holdMs = HOLD_MS,
}: LineGestureOptions): LineGestureHandlers {
  const pressRef = useRef<Press | null>(null);
  const clear = useCallback(() => {
    if (pressRef.current) clearTimeout(pressRef.current.timer);
    pressRef.current = null;
  }, []);
  useEffect(() => clear, [clear]);

  const onPointerDown = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      if (!enabled) return;
      const right = event.button === 2;
      const touch = event.pointerType === 'touch';
      if (!right && !touch) return;
      const target = event.target as HTMLElement;
      const onAvatar = Boolean(target.closest('[data-pose-avatar]'));
      if (onAvatar) {
        // The avatar's left-click and tap belong to its own menu; only its
        // right-click is ours.
        if (right) onMenu(event.clientX, event.clientY);
        return;
      }
      clear();
      const { clientX, clientY } = event;
      const press: Press = {
        right,
        opened: false,
        timer: setTimeout(() => {
          press.opened = true;
          onMenu(clientX, clientY);
        }, holdMs),
      };
      pressRef.current = press;
    },
    [enabled, onMenu, holdMs, clear]
  );

  const onPointerUp = useCallback(() => {
    const press = pressRef.current;
    if (press && !press.opened && press.right) onFold();
    clear();
  }, [onFold, clear]);

  const onContextMenu = useCallback(
    (event: MouseEvent<HTMLElement>) => {
      if (enabled) event.preventDefault();
    },
    [enabled]
  );

  return {
    onPointerDown,
    onPointerUp,
    onPointerCancel: clear,
    onPointerLeave: clear,
    onContextMenu,
  };
}
