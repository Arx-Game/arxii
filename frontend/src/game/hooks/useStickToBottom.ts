import { useEffect, useRef, useState, type MutableRefObject } from 'react';

/** How close to the end still counts as reading the newest line. */
const NEAR_BOTTOM_PX = 24;

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
      } else if (top < lastTop) {
        // Only a move up takes the reader off the bottom. Being away from it
        // without one is new content that has not been followed yet: the
        // event from an earlier follow can fire after the next line landed,
        // and reading that as "scrolled away" would stop the feed for good.
        pinnedRef.current = false;
      }
      lastTop = top;
    };

    // Following starts, or resumes after a view that was not live, on the
    // newest line if that is where the reader was.
    follow();
    container.addEventListener('scroll', track, { passive: true });
    const observer = new ResizeObserver(follow);
    observer.observe(container);
    if (content) observer.observe(content);
    return () => {
      container.removeEventListener('scroll', track);
      observer.disconnect();
    };
  }, [container, content, enabled]);

  return { containerRef: setContainer, contentRef: setContent, pinnedRef };
}
