import { useCallback, useEffect, useRef, type PointerEvent, type MouseEvent } from 'react';

/** How long a right-click or a touch is held before it is the menu, not the fold. */
export const HOLD_MS = 350;

/**
 * How long after a right press on a line the browser's own `contextmenu` is
 * still that press's: on Windows it fires after mouse-up, by which time a quick
 * fold has already shrunk the block and the event lands on whatever is under the
 * pointer now.
 */
const PRESS_CONTEXTMENU_MS = 1000;

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
  /** The line a touch press is holding selection off on, until it ends. */
  held: HTMLElement | null;
}

/** The event started inside the line itself, not in a menu or dialog portaled out of it. */
function inLine(event: { currentTarget: HTMLElement; target: EventTarget | null }): boolean {
  return event.target instanceof Node && event.currentTarget.contains(event.target);
}

/**
 * Swallow the browser's `contextmenu` for the press that just started, wherever
 * it lands: once, at document level, and before React sees it, so a line's own
 * handler only ever meets a keyboard-opened one.
 */
function swallowPressContextMenu(): void {
  const off = () => {
    document.removeEventListener('contextmenu', swallow, true);
    clearTimeout(timer);
  };
  const swallow = (event: Event) => {
    event.preventDefault();
    event.stopPropagation();
    off();
  };
  const timer = setTimeout(off, PRESS_CONTEXTMENU_MS);
  document.addEventListener('contextmenu', swallow, true);
}

/** iOS has no `contextmenu` to prevent: hold its selection and callout off for the press. */
function holdSelectionOff(element: HTMLElement): void {
  element.style.setProperty('user-select', 'none');
  element.style.setProperty('-webkit-user-select', 'none');
  element.style.setProperty('-webkit-touch-callout', 'none');
}

function releaseSelection(element: HTMLElement): void {
  element.style.removeProperty('user-select');
  element.style.removeProperty('-webkit-user-select');
  element.style.removeProperty('-webkit-touch-callout');
}

/**
 * The right button and the long-press on a feed line (#4128): the information
 * flow. A quick right-click on the text folds the line (and unfolds a folded
 * one); holding it opens the sorting menu; a right-click on the avatar
 * (`[data-pose-avatar]`) opens the menu at once; a touch held for the same
 * time is the menu too, and a plain tap is nothing, so scrolling on a phone
 * never folds. The browser's own context menu is suppressed for every press
 * that starts on the line; a `contextmenu` that arrives with no press (the
 * Menu key, Shift+F10) opens the sorting menu at its target, so the keyboard
 * reaches it too.
 *
 * Events from a menu or dialog the line portals out of itself (the avatar's
 * play menu, Look, Give mission) bubble back through React; none of them is a
 * gesture on the line.
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
    const press = pressRef.current;
    if (press) {
      clearTimeout(press.timer);
      if (press.held) releaseSelection(press.held);
    }
    pressRef.current = null;
  }, []);
  useEffect(() => clear, [clear]);

  const onPointerDown = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      if (!enabled || !inLine(event)) return;
      const right = event.button === 2;
      const touch = event.pointerType === 'touch';
      if (!right && !touch) return;
      if (right) swallowPressContextMenu();
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
      const held = touch ? event.currentTarget : null;
      if (held) holdSelectionOff(held);
      const press: Press = {
        right,
        opened: false,
        held,
        timer: setTimeout(() => {
          press.opened = true;
          onMenu(clientX, clientY);
        }, holdMs),
      };
      pressRef.current = press;
    },
    [enabled, onMenu, holdMs, clear]
  );

  const onPointerUp = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      const press = pressRef.current;
      if (press && !press.opened && press.right && inLine(event)) onFold();
      clear();
    },
    [onFold, clear]
  );

  const onContextMenu = useCallback(
    (event: MouseEvent<HTMLElement>) => {
      if (!enabled || !inLine(event)) return;
      event.preventDefault();
      // A press in progress (a touch being held) is already handled; with none,
      // this came from the keyboard: the menu opens under the focused element.
      if (pressRef.current) return;
      const anchor =
        (event.target as HTMLElement).closest('[data-pose-avatar]') ?? event.currentTarget;
      const rect = anchor.getBoundingClientRect();
      onMenu(rect.left, rect.bottom);
    },
    [enabled, onMenu]
  );

  return {
    onPointerDown,
    onPointerUp,
    onPointerCancel: clear,
    onPointerLeave: clear,
    onContextMenu,
  };
}
