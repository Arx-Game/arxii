import { useEffect, useRef, useState, type MutableRefObject } from 'react';

/** How close to the end still counts as reading the newest line. */
const NEAR_BOTTOM_PX = 24;

/**
 * How long after a wheel turn, a touch or a key press a move up is still the
 * reader's. A scroll the reader starts keeps moving for a few frames after
 * the input that started it.
 */
const READER_INPUT_WINDOW_MS = 500;

/** Whether a scroll container is showing the end of its content. */
export function isNearBottom(container: HTMLElement): boolean {
  return container.scrollHeight - container.scrollTop - container.clientHeight < NEAR_BOTTOM_PX;
}

export interface StickToBottom {
  /** Ref for the element that scrolls. */
  containerRef: (element: HTMLElement | null) => void;
  /** Ref for the element inside it whose height is the content's. */
  contentRef: (element: HTMLElement | null) => void;
  /**
   * Whether the reader is at the newest content. The hook keeps it from the
   * reader's own scrolling; a caller that puts the reader somewhere itself (a
   * restored position, a tab switch) writes it to say which it was.
   */
  pinnedRef: MutableRefObject<boolean>;
}

/**
 * Keeps a feed on its newest line while the reader is at the bottom, and
 * leaves it alone once they scroll up to read.
 *
 * It follows the content's size, not a count of items: a feed grows when a
 * pose arrives, and also when a note does, when a virtualised row is measured
 * taller than its estimate, and when an image loads. A `ResizeObserver` on the
 * content sees all of them; one on the container keeps the last line in view
 * when the composer grows and the feed above it gets shorter.
 *
 * Only the reader takes the feed off the bottom: a move up that follows a
 * wheel turn, a touch, a key press, or a pointer held down on the scrollbar.
 * The position also moves up with nobody touching it, when a virtualised list
 * measures rows shorter than it estimated and corrects for the difference,
 * and it can be far from the bottom at that moment because newer rows have
 * not been followed yet. Reading that as "scrolled away" stopped
 * Chronological from following in about one run in two.
 *
 * `enabled` false stops both the following and the tracking, for a view that
 * is not live (a historical reference).
 */
export function useStickToBottom(enabled = true): StickToBottom {
  const [container, setContainer] = useState<HTMLElement | null>(null);
  const [content, setContent] = useState<HTMLElement | null>(null);
  const pinnedRef = useRef(true);

  useEffect(() => {
    if (!container || !enabled) return;
    let lastTop = container.scrollTop;
    let lastInputAt = Number.NEGATIVE_INFINITY;
    let pointerHeld = false;

    const noteInput = () => {
      lastInputAt = performance.now();
    };
    const holdPointer = () => {
      pointerHeld = true;
    };
    const releasePointer = () => {
      if (!pointerHeld) return;
      pointerHeld = false;
      // A drag that is let go can still be settling.
      lastInputAt = performance.now();
    };
    const readerIsScrolling = () =>
      pointerHeld || performance.now() - lastInputAt < READER_INPUT_WINDOW_MS;

    const follow = () => {
      if (!pinnedRef.current) return;
      container.scrollTop = container.scrollHeight;
      // The move is this hook's own; the next one up is measured from here.
      lastTop = container.scrollTop;
    };

    const track = () => {
      const top = container.scrollTop;
      if (isNearBottom(container)) {
        pinnedRef.current = true;
      } else if (top < lastTop && readerIsScrolling()) {
        pinnedRef.current = false;
      }
      lastTop = top;
    };

    // Following starts, or resumes after a view that was not live, on the
    // newest line if that is where the reader was.
    follow();
    container.addEventListener('scroll', track, { passive: true });
    container.addEventListener('wheel', noteInput, { passive: true });
    container.addEventListener('touchmove', noteInput, { passive: true });
    container.addEventListener('keydown', noteInput);
    container.addEventListener('pointerdown', holdPointer);
    window.addEventListener('pointerup', releasePointer);
    window.addEventListener('pointercancel', releasePointer);
    const observer = new ResizeObserver(follow);
    observer.observe(container);
    if (content) observer.observe(content);
    return () => {
      container.removeEventListener('scroll', track);
      container.removeEventListener('wheel', noteInput);
      container.removeEventListener('touchmove', noteInput);
      container.removeEventListener('keydown', noteInput);
      container.removeEventListener('pointerdown', holdPointer);
      window.removeEventListener('pointerup', releasePointer);
      window.removeEventListener('pointercancel', releasePointer);
      observer.disconnect();
    };
  }, [container, content, enabled]);

  return { containerRef: setContainer, contentRef: setContent, pinnedRef };
}
