import '@testing-library/jest-dom/vitest';
import { afterEach, beforeEach, vi } from 'vitest';
import React from 'react';

// Polyfill ResizeObserver — not available in jsdom but required by Radix UI components
// (use-size hook in @radix-ui/react-use-size uses it for layout measurements)
globalThis.ResizeObserver ??= class ResizeObserver {
  // Intentional no-op stub: jsdom has no layout engine, so there is nothing to observe.
  observe(): void {
    return undefined;
  }
  // Intentional no-op stub: nothing was ever observed, so there is nothing to stop observing.
  unobserve(): void {
    return undefined;
  }
  // Intentional no-op stub: no observation state exists to tear down.
  disconnect(): void {
    return undefined;
  }
};

// Polyfill IntersectionObserver — not available in jsdom but constructed by
// usePoseReadTracking.ts (dwell-tracked read state) whenever a component that
// uses it mounts in a test (e.g. ThreadedNarrativeReader.tsx). A no-op stub is
// correct here: jsdom never fires real intersection callbacks, so tests that
// need to exercise dwell-tracking stub this global themselves
// (usePoseReadTracking.test.ts) — this default only prevents unrelated tests
// from throwing "IntersectionObserver is not defined".
globalThis.IntersectionObserver ??= class IntersectionObserver {
  // Intentional no-op stub: jsdom fires no real intersection events.
  observe(): void {
    return undefined;
  }
  unobserve(): void {
    return undefined;
  }
  disconnect(): void {
    return undefined;
  }
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
} as unknown as typeof IntersectionObserver;

// Polyfill hasPointerCapture / setPointerCapture / releasePointerCapture — not available
// in jsdom but required by Radix UI Select pointer-event handling (select.tsx:323).
// Without this, userEvent.click on a Radix Select trigger throws in tests.
if (!window.HTMLElement.prototype.hasPointerCapture) {
  window.HTMLElement.prototype.hasPointerCapture = () => false;
}
if (!window.HTMLElement.prototype.setPointerCapture) {
  window.HTMLElement.prototype.setPointerCapture = () => {};
}
if (!window.HTMLElement.prototype.releasePointerCapture) {
  window.HTMLElement.prototype.releasePointerCapture = () => {};
}

// Polyfill scrollIntoView — not available in jsdom but called by Radix UI Select
// when it tries to scroll the selected item into view (select.tsx:590).
if (!window.Element.prototype.scrollIntoView) {
  window.Element.prototype.scrollIntoView = () => {};
}

// Polyfill PointerEvent — jsdom has no PointerEvent (longstanding gap —
// https://github.com/jsdom/jsdom/issues/2527), so `fireEvent.pointerDown/Move/Up`
// deliver events with no clientX/clientY/button at all without this. Any test that
// drives a pointer-drag interaction (e.g. LookDialog.test.tsx's title-bar drag) needs it.
if (typeof window.PointerEvent === 'undefined') {
  class PointerEventPolyfill extends MouseEvent {
    // `pointerType` is how code tells a touch from a mouse (a long-press is
    // the touch form of a held right-click, #4128); carry it from the init.
    readonly pointerType: string;
    constructor(type: string, params: PointerEventInit = {}) {
      super(type, params);
      this.pointerType = params.pointerType ?? 'mouse';
    }
  }
  // @ts-expect-error jsdom doesn't implement PointerEvent
  window.PointerEvent = PointerEventPolyfill;
}

// Mock framer-motion to disable animations in tests
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');

  // Filter out motion-specific props, which a plain element does not take.
  const motionProps = new Set([
    'initial',
    'animate',
    'exit',
    'transition',
    'variants',
    'whileHover',
    'whileTap',
    'onAnimationStart',
    'onAnimationComplete',
  ]);
  const filterProps = (props: Record<string, unknown>) =>
    Object.fromEntries(Object.entries(props).filter(([key]) => !motionProps.has(key)));

  type MotionComponentProps = {
    children?: React.ReactNode;
  } & Record<string, unknown>;

  return {
    ...actual,
    motion: {
      div: ({ children, ...props }: MotionComponentProps) =>
        React.createElement('div', filterProps(props), children),
      span: ({ children, ...props }: MotionComponentProps) =>
        React.createElement('span', filterProps(props), children),
      button: ({ children, ...props }: MotionComponentProps) =>
        React.createElement('button', filterProps(props), children),
    },
  };
});

// Fail any test that makes React, Radix or react-redux log one of their
// development warnings (#4677). They were ~2,500 lines of every CI log and hid
// the real failures; each one is a test that let an update escape act(), a
// dialog with no description, or a component bug (a duplicate key, invalid DOM
// nesting, a selector that builds a new object every call). The message still
// prints, so the failing test shows what to fix.
// Limits: the check runs in the last afterEach (vitest's default hook order),
// after Testing Library has unmounted; a test that silences console.error with
// its own spy also silences this; a warning logged after a test's teardown is
// not caught.
const DEV_WARNINGS = [
  'not wrapped in act(',
  'Missing `Description` or `aria-describedby={undefined}`',
  'Encountered two children with the same key',
  'validateDOMNesting',
  'Unknown event handler property',
  'Function components cannot be given refs',
  'returned a different result when called with the same parameters',
];
const caughtWarnings: string[] = [];
for (const level of ['error', 'warn'] as const) {
  const original = console[level].bind(console);
  console[level] = (...args: unknown[]) => {
    // React passes a `%s` format string; fill it so the message names the component.
    const [first, ...rest] = args;
    const text =
      typeof first === 'string'
        ? first.replace(/%s/g, () => String(rest.shift() ?? ''))
        : args.map(String).join(' ');
    const match = DEV_WARNINGS.find((needle) => text.includes(needle));
    if (match) caughtWarnings.push(text.split('\n')[0]);
    original(...args);
  };
}
beforeEach(() => {
  caughtWarnings.length = 0;
});
afterEach(() => {
  if (caughtWarnings.length === 0) return;
  const unique = [...new Set(caughtWarnings)];
  caughtWarnings.length = 0;
  throw new Error(`React development warning during this test:\n${unique.join('\n')}`);
});

// Add Vitest global types
declare global {
  const describe: typeof import('vitest').describe;
  const it: typeof import('vitest').it;
  const test: typeof import('vitest').test;
  const expect: typeof import('vitest').expect;
  const beforeAll: typeof import('vitest').beforeAll;
  const afterAll: typeof import('vitest').afterAll;
  const beforeEach: typeof import('vitest').beforeEach;
  const afterEach: typeof import('vitest').afterEach;
  const vi: typeof import('vitest').vi;
}
