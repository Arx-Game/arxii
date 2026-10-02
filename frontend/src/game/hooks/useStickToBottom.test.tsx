import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { stubResizeObserver, type ResizeObserverStub } from '@/test/utils/resizeObserver';
import { useStickToBottom } from './useStickToBottom';

function Feed({ enabled }: { enabled?: boolean }) {
  const stick = useStickToBottom(enabled);
  return (
    <div data-testid="container" ref={stick.containerRef}>
      <div data-testid="content" ref={stick.contentRef} />
    </div>
  );
}

const VIEWPORT = 400;

/** jsdom lays nothing out: give the container the heights a browser would report. */
function setContentHeight(container: HTMLElement, height: number): void {
  Object.defineProperty(container, 'scrollHeight', { value: height, configurable: true });
  Object.defineProperty(container, 'clientHeight', { value: VIEWPORT, configurable: true });
}

/** The reader moves the scrollbar: the position changes, then the event fires. */
function scrollTo(container: HTMLElement, top: number): void {
  container.scrollTop = top;
  fireEvent.scroll(container);
}

describe('useStickToBottom', () => {
  let observer: ResizeObserverStub;

  beforeEach(() => {
    observer = stubResizeObserver();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /** A container resting at the bottom of 1000px of content. */
  function renderAtBottom(enabled?: boolean): HTMLElement {
    render(<Feed enabled={enabled} />);
    const container = screen.getByTestId('container');
    setContentHeight(container, 1000);
    scrollTo(container, 1000 - VIEWPORT);
    return container;
  }

  /** New content arrives: the content is taller, and the browser tells the observer. */
  function grow(container: HTMLElement, height: number): void {
    setContentHeight(container, height);
    act(() => observer.resize());
  }

  it('watches the container and its content', () => {
    render(<Feed />);
    expect(observer.observed()).toEqual(
      expect.arrayContaining([screen.getByTestId('container'), screen.getByTestId('content')])
    );
  });

  it('follows new content while the reader is at the bottom', () => {
    const container = renderAtBottom();

    grow(container, 1200);

    expect(container.scrollTop).toBe(1200);
  });

  it('starts out following, before the reader has scrolled at all', () => {
    render(<Feed />);
    const container = screen.getByTestId('container');

    grow(container, 1000);

    expect(container.scrollTop).toBe(1000);
  });

  it('leaves the reader alone once they scroll up', () => {
    const container = renderAtBottom();

    scrollTo(container, 200);
    grow(container, 1200);

    expect(container.scrollTop).toBe(200);
  });

  it('follows again once the reader returns to the bottom', () => {
    const container = renderAtBottom();
    scrollTo(container, 200);

    // Within a line or so of the end counts as the end.
    scrollTo(container, 1000 - VIEWPORT - 10);
    grow(container, 1200);

    expect(container.scrollTop).toBe(1200);
  });

  it('keeps following when a scroll event lands between new content and its follow', () => {
    const container = renderAtBottom();

    // The content is already taller when the event from an earlier follow
    // fires, so the position reads as far from the bottom. The reader did not
    // move; the observer has not caught up yet.
    setContentHeight(container, 1200);
    fireEvent.scroll(container);
    act(() => observer.resize());

    expect(container.scrollTop).toBe(1200);
  });

  it('stays off the bottom while the reader scrolls back down without reaching it', () => {
    const container = renderAtBottom();
    scrollTo(container, 100);

    scrollTo(container, 300);
    grow(container, 1200);

    expect(container.scrollTop).toBe(300);
  });

  it('keeps the bottom in view when the container itself gets shorter', () => {
    const container = renderAtBottom();

    // The composer grew a line: same content, smaller viewport.
    Object.defineProperty(container, 'clientHeight', { value: 350, configurable: true });
    act(() => observer.resize());

    expect(container.scrollTop).toBe(1000);
  });

  it('neither follows nor tracks while disabled', () => {
    const container = renderAtBottom(false);

    grow(container, 1200);

    expect(container.scrollTop).toBe(600);
    expect(observer.observed()).toEqual([]);
  });

  it('lets a caller that restores a position say the reader is not at the bottom', () => {
    let pinned: { current: boolean } | undefined;
    function Restoring() {
      const stick = useStickToBottom();
      pinned = stick.pinnedRef;
      return (
        <div data-testid="container" ref={stick.containerRef}>
          <div ref={stick.contentRef} />
        </div>
      );
    }
    render(<Restoring />);
    const container = screen.getByTestId('container');
    setContentHeight(container, 1000);

    if (pinned) pinned.current = false;
    grow(container, 1200);

    expect(container.scrollTop).toBe(0);
  });
});
