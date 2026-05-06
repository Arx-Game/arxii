import '@testing-library/jest-dom';
import { vi } from 'vitest';
import React from 'react';

// Polyfill ResizeObserver — not available in jsdom but required by Radix UI components
// (use-size hook in @radix-ui/react-use-size uses it for layout measurements)
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

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

// Mock framer-motion to disable animations in tests
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');

  // Filter out motion-specific props
  const filterProps = (props: Record<string, unknown>) => {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { initial, animate, exit, transition, variants, whileHover, whileTap, ...rest } = props;
    return rest;
  };

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
